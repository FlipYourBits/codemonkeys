"""Bundled skills — node behavior and language guidance.

Node skill modules export descriptive constants (``CODE_REVIEW``,
``SECURITY_AUDIT``, ``DOCS_REVIEW``) used by the corresponding nodes.

Language modules (``python``, ``javascript``, ``rust``) export
``CLEAN_CODE`` and ``SECURITY`` constants. Pass them via
``extra_skills`` on any node factory.

Example::

    from langclaude.skills import PYTHON_CLEAN_CODE

    implement_feature_node(extra_skills=[PYTHON_CLEAN_CODE])
"""

from langclaude.skills.code_review import CODE_REVIEW as CODE_REVIEW_SKILL
from langclaude.skills.docs_review import DOCS_REVIEW as DOCS_REVIEW_SKILL
from langclaude.skills.javascript import CLEAN_CODE as JAVASCRIPT_CLEAN_CODE
from langclaude.skills.javascript import SECURITY as JAVASCRIPT_SECURITY
from langclaude.skills.python import CLEAN_CODE as PYTHON_CLEAN_CODE
from langclaude.skills.python import SECURITY as PYTHON_SECURITY
from langclaude.skills.rust import CLEAN_CODE as RUST_CLEAN_CODE
from langclaude.skills.rust import SECURITY as RUST_SECURITY
from langclaude.skills.security_audit import SECURITY_AUDIT as SECURITY_AUDIT_SKILL

__all__ = [
    "CODE_REVIEW_SKILL",
    "DOCS_REVIEW_SKILL",
    "JAVASCRIPT_CLEAN_CODE",
    "JAVASCRIPT_SECURITY",
    "PYTHON_CLEAN_CODE",
    "PYTHON_SECURITY",
    "RUST_CLEAN_CODE",
    "RUST_SECURITY",
    "SECURITY_AUDIT_SKILL",
]
