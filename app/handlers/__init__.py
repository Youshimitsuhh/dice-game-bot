# app/handlers/__init__.py
from .commands import register_command_handlers
from .buttons import register_button_handlers
from .messages import register_message_handlers
from .lobby_handlers import register_lobby_handlers

__all__ = [
    'register_command_handlers',
    'register_button_handlers',
    'register_message_handlers',
    'register_lobby_handlers'
]