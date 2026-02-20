"""
Terminal UI framework for the agent skills engine.

Provides components for building interactive terminal interfaces including
text input, multi-line editing, markdown rendering, select lists, overlays,
keybinding management, and autocomplete.
"""
from __future__ import annotations

from agent_skills_engine.tui.autocomplete import (
    AutocompleteProvider,
    CombinedAutocomplete,
    CommandAutocomplete,
    FileAutocomplete,
    SlashCommand,
    Suggestion,
)
from agent_skills_engine.tui.component import Component
from agent_skills_engine.tui.container import Container
from agent_skills_engine.tui.editor_widget import EditorWidget
from agent_skills_engine.tui.input_widget import InputWidget
from agent_skills_engine.tui.keybindings import DEFAULT_KEYBINDINGS, KeybindingsManager
from agent_skills_engine.tui.keys import Key, parse_key
from agent_skills_engine.tui.markdown_widget import MarkdownWidget
from agent_skills_engine.tui.overlay import OverlayManager
from agent_skills_engine.tui.renderer import TUIRenderer
from agent_skills_engine.tui.select_list import ListItem, SelectList

__all__ = [
    # Core
    "Component",
    "Container",
    "TUIRenderer",
    # Keys
    "Key",
    "parse_key",
    # Widgets
    "InputWidget",
    "EditorWidget",
    "MarkdownWidget",
    "SelectList",
    "ListItem",
    # Overlay
    "OverlayManager",
    # Keybindings
    "KeybindingsManager",
    "DEFAULT_KEYBINDINGS",
    # Autocomplete
    "AutocompleteProvider",
    "CombinedAutocomplete",
    "CommandAutocomplete",
    "FileAutocomplete",
    "SlashCommand",
    "Suggestion",
]
