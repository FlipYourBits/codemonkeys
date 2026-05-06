from __future__ import annotations

from codemonkeys.core.prompts.code_quality import CODE_QUALITY
from codemonkeys.core.prompts.design_review import DESIGN_REVIEW
from codemonkeys.core.prompts.diff_context import DIFF_CONTEXT_TEMPLATE
from codemonkeys.core.prompts.engineering_mindset import ENGINEERING_MINDSET
from codemonkeys.core.prompts.hardening_checklist import HARDENING_CHECKLIST
from codemonkeys.core.prompts.python_cmd import PYTHON_CMD
from codemonkeys.core.prompts.python_guidelines import PYTHON_GUIDELINES
from codemonkeys.core.prompts.python_source_filter import PYTHON_SOURCE_FILTER
from codemonkeys.core.prompts.resilience_review import RESILIENCE_REVIEW
from codemonkeys.core.prompts.security_observations import SECURITY_OBSERVATIONS
from codemonkeys.core.prompts.test_quality import TEST_QUALITY

__all__ = [
    "CODE_QUALITY",
    "DESIGN_REVIEW",
    "DIFF_CONTEXT_TEMPLATE",
    "ENGINEERING_MINDSET",
    "HARDENING_CHECKLIST",
    "PYTHON_CMD",
    "PYTHON_GUIDELINES",
    "PYTHON_SOURCE_FILTER",
    "RESILIENCE_REVIEW",
    "SECURITY_OBSERVATIONS",
    "TEST_QUALITY",
]
