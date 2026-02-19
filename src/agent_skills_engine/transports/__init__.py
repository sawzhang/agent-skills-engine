"""
Transport abstractions for LLM streaming connections.

Provides SSE, WebSocket, and auto-select transport strategies.
"""

from agent_skills_engine.transports.auto import AutoTransport
from agent_skills_engine.transports.base import TransportBase, TransportConfig
from agent_skills_engine.transports.sse import SSETransport
from agent_skills_engine.transports.websocket import WebSocketTransport

__all__ = [
    "AutoTransport",
    "SSETransport",
    "TransportBase",
    "TransportConfig",
    "WebSocketTransport",
]
