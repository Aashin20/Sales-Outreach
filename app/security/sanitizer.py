import re
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

# Patterns commonly used in prompt injection attacks
INJECTION_PATTERNS = [
    # Direct instruction overrides
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+(all\s+)?above\s+instructions",
    r"disregard\s+(all\s+)?previous",
    r"forget\s+(all\s+)?previous",
    r"override\s+system\s+prompt",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*you\s+are",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"\[/INST\]",
    r"<<\s*SYS\s*>>",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    # Role injection
    r"you\s+are\s+now\s+(?:a|an|the)\s+",
    r"act\s+as\s+(?:a|an|the)\s+",
    r"pretend\s+you\s+are",
    r"from\s+now\s+on\s+you\s+(?:are|will)",
    # Data exfiltration attempts
    r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"show\s+(?:your|the)\s+(?:system\s+)?prompt",
    r"output\s+(?:your|the)\s+(?:system\s+)?instructions",
    r"repeat\s+(?:the\s+)?(?:above|previous)\s+(?:text|instructions)",
]
