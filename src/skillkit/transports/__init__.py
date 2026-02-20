"""
Transport abstractions for LLM streaming connections.

Provides SSE, WebSocket, and auto-select transport strategies.
"""

from skillkit.transports.auto import AutoTransport
from skillkit.transports.base import TransportBase, TransportConfig
from skillkit.transports.sse import SSETransport
from skillkit.transports.websocket import WebSocketTransport

__all__ = [
    "AutoTransport",
    "SSETransport",
    "TransportBase",
    "TransportConfig",
    "WebSocketTransport",
]
