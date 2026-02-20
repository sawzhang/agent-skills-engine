"""
Session management module.

Provides JSONL-based session persistence with a tree structure for
branching conversations.  Mirrors the pi-mono session-manager patterns
adapted for Python.
"""

from agent_skills_engine.session.manager import SessionManager
from agent_skills_engine.session.models import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionContext,
    SessionEntry,
    SessionEntryType,
    SessionHeader,
    SessionInfoEntry,
    SessionMessageEntry,
    ThinkingLevelChangeEntry,
)
from agent_skills_engine.session.store import (
    append_entry,
    get_session_dir,
    list_sessions,
    load_session,
    save_header,
)
from agent_skills_engine.session.tree import (
    SessionTreeNode,
    build_tree,
    find_entry,
    get_branches,
    walk_to_root,
)

__all__ = [
    # Manager
    "SessionManager",
    # Models
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "LabelEntry",
    "ModelChangeEntry",
    "SessionContext",
    "SessionEntry",
    "SessionEntryType",
    "SessionHeader",
    "SessionInfoEntry",
    "SessionMessageEntry",
    "ThinkingLevelChangeEntry",
    # Store
    "append_entry",
    "get_session_dir",
    "list_sessions",
    "load_session",
    "save_header",
    # Tree
    "SessionTreeNode",
    "build_tree",
    "find_entry",
    "get_branches",
    "walk_to_root",
]
