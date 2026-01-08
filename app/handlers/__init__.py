# app/handlers/__init__.py
from .commands import register_command_handlers
from .buttons import register_button_handlers
from .messages import register_message_handlers
from .lobby_handlers import register_lobby_handlers
from .game_handlers import register_game_handlers
from .duel_handlers import register_duel_handlers
from .payment_handlers import register_payment_handlers

__all__ = [
    'register_command_handlers',
    'register_button_handlers',
    'register_message_handlers',
    'register_lobby_handlers',
    'register_game_handlers',
    'register_duel_handlers',
    'register_payment_handlers',
]