"""
Terminal UI framework for the skillkit.

Provides components for building interactive terminal interfaces including
text input, multi-line editing, markdown rendering, select lists, overlays,
keybinding management, and autocomplete.
"""
from __future__ import annotations

from skillkit.tui.autocomplete import (
    AutocompleteProvider,
    CombinedAutocomplete,
    CommandAutocomplete,
    FileAutocomplete,
    SlashCommand,
    Suggestion,
)
from skillkit.tui.component import Component
from skillkit.tui.container import Container
from skillkit.tui.editor_widget import EditorWidget
from skillkit.tui.input_widget import InputWidget
from skillkit.tui.keybindings import DEFAULT_KEYBINDINGS, KeybindingsManager
from skillkit.tui.keys import Key, parse_key
from skillkit.tui.markdown_widget import MarkdownWidget
from skillkit.tui.overlay import OverlayManager
from skillkit.tui.renderer import TUIRenderer
from skillkit.tui.select_list import ListItem, SelectList

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
