"""Utilities module initialization."""

from .database_utils import get_connection  # Change from .database to .database_utils
from .thinking_log_viewer import render_thinking_log_viewer

__all__ = [
    'get_connection',
    'render_thinking_log_viewer'
]