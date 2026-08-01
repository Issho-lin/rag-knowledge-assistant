"""知识库分库与 Profile 注册。"""

from .profiles import COMMON_PROFILE, KBProfile, PDF_PROFILE, POLICIES_PROFILE, TABULAR_PROFILE
from .registry import KnowledgeBase, get_kb, kb_profile_for_doc, list_kbs, resolve_kb_id

__all__ = [
    "COMMON_PROFILE",
    "TABULAR_PROFILE",
    "KBProfile",
    "PDF_PROFILE",
    "POLICIES_PROFILE",
    "KnowledgeBase",
    "get_kb",
    "kb_profile_for_doc",
    "list_kbs",
    "resolve_kb_id",
]
