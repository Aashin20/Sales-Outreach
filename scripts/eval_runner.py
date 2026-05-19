"""
Eval harness — re-runs pick_hook and compose_message LLM calls against
the labelled eval set and reports precision/recall/quality metrics.

Usage:
    python scripts/eval_runner.py
    python scripts/eval_runner.py --tool pick_hook
    python scripts/eval_runner.py --tool compose_message
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.services.llm import LLMClient, HookResult, OutreachMessage


def load_eval_set(tool_name: str) -> list[dict]:
    """Load eval JSONL file."""
    eval_path = Path(__file__).parent.parent / "evals" / f"{tool_name}_eval.jsonl"
    examples = []
    with open(eval_path) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))
    return examples


async def eval_pick_hook(client: LLMClient, examples: list[dict]) -> dict:
    """Evaluate pick_hook against labelled examples."""
    results = []
    correct_category = 0
    confidence_in_range = 0
    evidence_matches = 0
    total = len(examples)
    errors = 0

    for ex in examples:
        try:
            signals = {
                "homepage": ex.get("homepage"),
                "news": ex.get("news"),
                "profile": ex.get("profile"),
            }

            start = time.monotonic()
            hook_result, stats = await client.pick_hook(
                company_signals=signals,
                person_name=ex["person_name"],
                domain=ex["domain"],
            )
            latency = (time.monotonic() - start) * 1000

            # Check category match (fuzzy — check if expected category appears in hook or reasoning)
            expected_cat = ex["expected_hook"]
            cat_words = expected_cat.replace("_", " ").split()
            hook_text = f"{hook_result.hook} {hook_result.reasoning}".lower()
            cat_match = any(w in hook_text for w in cat_words) or expected_cat == "generic"
            if cat_match:
                correct_category += 1

            # Check confidence range
            conf_min = ex.get("confidence_min", 0.0)
            conf_max = ex.get("confidence_max", 1.0)
            if conf_min <= hook_result.confidence <= conf_max:
                confidence_in_range += 1

            # Check evidence keywords
            ev_keywords = ex.get("evidence_keywords", [])
            if ev_keywords:
                evidence_text = " ".join(hook_result.evidence).lower()
                matched = sum(1 for kw in ev_keywords if kw.lower() in evidence_text)
                if matched >= len(ev_keywords) * 0.5:  # At least 50% of keywords found
                    evidence_matches += 1
            else:
                evidence_matches += 1  # No keywords expected = pass

            results.append({
                "id": ex["id"],
                "domain": ex["domain"],
                "status": "pass" if cat_match else "fail",
                "expected_category": expected_cat,
                "got_hook": hook_result.hook[:80],
                "got_confidence": hook_result.confidence,
                "category_match": cat_match,
                "confidence_ok": conf_min <= hook_result.confidence <= conf_max,
                "latency_ms": int(latency),
                "cost_usd": stats["cost_usd"],
            })

        except Exception as e:
            errors += 1
            results.append({
                "id": ex["id"],
                "domain": ex["domain"],
                "status": "error",
                "error": str(e)[:200],
            })

    return {
        "tool": "pick_hook",
        "total": total,
        "errors": errors,
        "category_precision": correct_category / max(total - errors, 1),
        "confidence_accuracy": confidence_in_range / max(total - errors, 1),
        "evidence_recall": evidence_matches / max(total - errors, 1),
        "results": results,
    }


async def eval_compose_message(client: LLMClient, examples: list[dict]) -> dict:
    """Evaluate compose_message against labelled examples."""
    results = []
    personalized = 0
    has_cta = 0
    under_word_limit = 0
    total = len(examples)
    errors = 0

    for ex in examples:
        try:
            hook_result = HookResult(
                hook=ex["hook"],
                reasoning=ex["reasoning"],
                evidence=ex["evidence"],
                confidence=ex["confidence"],
            )

            start = time.monotonic()
            msg_result, stats = await client.compose_message(
                hook_result=hook_result,
                person_name=ex["person_name"],
                domain=ex["domain"],
            )
            latency = (time.monotonic() - start) * 1000

            # Check personalization
            first_name = ex["person_name"].split()[0]
            is_personalized = (
                first_name.lower() in msg_result.body.lower()
                or ex["domain"].split(".")[0] in msg_result.body.lower()
            )
            if is_personalized:
                personalized += 1

            # Check CTA
            cta_present = len(msg_result.call_to_action) > 10
            if cta_present:
                has_cta += 1

            # Check word count
            word_count = len(msg_result.body.split())
            max_words = ex.get("expected_max_words", 150)
            within_limit = word_count <= max_words + 20  # 20-word grace
            if within_limit:
                under_word_limit += 1

            results.append({
                "id": ex["id"],
                "domain": ex["domain"],
                "status": "pass" if (is_personalized and cta_present) else "fail",
                "personalized": is_personalized,
                "has_cta": cta_present,
                "word_count": word_count,
                "within_limit": within_limit,
                "subject": msg_result.subject[:60],
                "tone": msg_result.tone,
                "latency_ms": int(latency),
                "cost_usd": stats["cost_usd"],
            })

        except Exception as e:
            errors += 1
            results.append({
                "id": ex["id"],
                "domain": ex["domain"],
                "status": "error",
                "error": str(e)[:200],
            })

    return {
        "tool": "compose_message",
        "total": total,
        "errors": errors,
        "personalization_rate": personalized / max(total - errors, 1),
        "cta_rate": has_cta / max(total - errors, 1),
        "word_limit_compliance": under_word_limit / max(total - errors, 1),
        "results": results,
    }


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run LLM eval harness")
    parser.add_argument("--tool", choices=["pick_hook", "compose_message", "all"], default="all")
    parser.add_argument("--output", default="evals/eval_results.json")
    args = parser.parse_args()

    settings = get_settings()
    client = LLMClient(settings)
    all_results = {}

    if args.tool in ("pick_hook", "all"):
        print("=" * 60)
        print("Running pick_hook evals...")
        print("=" * 60)
        examples = load_eval_set("pick_hook")
        result = await eval_pick_hook(client, examples)
        all_results["pick_hook"] = result
        print(f"  Category Precision: {result['category_precision']:.1%}")
        print(f"  Confidence Accuracy: {result['confidence_accuracy']:.1%}")
        print(f"  Evidence Recall: {result['evidence_recall']:.1%}")
        print(f"  Errors: {result['errors']}/{result['total']}")

    if args.tool in ("compose_message", "all"):
        print("=" * 60)
        print("Running compose_message evals...")
        print("=" * 60)
        examples = load_eval_set("compose_message")
        result = await eval_compose_message(client, examples)
        all_results["compose_message"] = result
        print(f"  Personalization Rate: {result['personalization_rate']:.1%}")
        print(f"  CTA Rate: {result['cta_rate']:.1%}")
        print(f"  Word Limit Compliance: {result['word_limit_compliance']:.1%}")
        print(f"  Errors: {result['errors']}/{result['total']}")

    # Save results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "timestamp": datetime.utcnow().isoformat(),
            "results": all_results,
        }, f, indent=2, default=str)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
