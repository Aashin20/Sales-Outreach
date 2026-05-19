#!/bin/bash
# =============================================================================
# Outreach Intelligence API — Evaluator Walkthrough
# =============================================================================
# This script walks through the full API flow:
#   1. Health check
#   2. Submit a job
#   3. Poll for result
#   4. Submit feedback
#
# Prerequisites:
#   - API running at localhost:8000
#   - An API key (run: python scripts/seed_api_keys.py)
#
# Usage:
#   export API_KEY="oai_your_key_here"
#   bash scripts/curl_walkthrough.sh
# =============================================================================

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-your_api_key_here}"

echo "============================================"
echo "Outreach Intelligence API — Walkthrough"
echo "============================================"
echo "Base URL: $BASE_URL"
echo ""

# ── Step 1: Health Check ─────────────────────────────────────────
echo "── Step 1: Liveness Check (healthz) ──"
curl -s "$BASE_URL/v1/healthz" | python -m json.tool
echo ""

echo "── Step 1b: Readiness Check (readyz) ──"
curl -s "$BASE_URL/v1/readyz" | python -m json.tool
echo ""

# ── Step 2: Submit a Job ─────────────────────────────────────────
echo "── Step 2: Submit Outreach Job ──"
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE_URL/v1/outreach" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "domain": "stripe.com",
    "person_name": "Sarah Chen"
  }')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "Status: $HTTP_CODE"
echo "$BODY" | python -m json.tool

JOB_ID=$(echo "$BODY" | python -c "import sys,json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)
echo "Job ID: $JOB_ID"
echo ""

if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
  echo "❌ Failed to get job ID. Check your API key."
  exit 1
fi

# ── Step 3: Poll for Result ──────────────────────────────────────
echo "── Step 3: Polling for Result ──"
for i in $(seq 1 12); do
  echo "  Poll attempt $i..."
  POLL=$(curl -s \
    -H "X-API-Key: $API_KEY" \
    "$BASE_URL/v1/outreach/$JOB_ID")

  STATUS=$(echo "$POLL" | python -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  echo "  Status: $STATUS"

  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    echo ""
    echo "Final result:"
    echo "$POLL" | python -m json.tool
    break
  fi

  sleep 5
done
echo ""

# ── Step 4: Submit Feedback ──────────────────────────────────────
echo "── Step 4: Submit Feedback ──"
curl -s -X POST "$BASE_URL/v1/outreach/$JOB_ID/feedback" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "rating": "thumbs_up",
    "comment": "Great hook, very relevant!",
    "hook_quality": 4,
    "message_quality": 5,
    "evidence_accuracy": true
  }' | python -m json.tool
echo ""

# ── Step 5: Resubmit (Idempotency Test) ─────────────────────────
echo "── Step 5: Resubmit Same Prospect (Idempotency) ──"
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -X POST "$BASE_URL/v1/outreach" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "domain": "stripe.com",
    "person_name": "Sarah Chen"
  }' | python -m json.tool
echo "(Should return 200 with cached result)"
echo ""

echo "============================================"
echo "✅ Walkthrough complete!"
echo ""
echo "Additional endpoints to explore:"
echo "  Swagger UI:  $BASE_URL/docs"
echo "  ReDoc:       $BASE_URL/redoc"
echo "  Dashboard:   http://localhost:8501"
echo "============================================"
