# app/keyboards/game_keyboards.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_bet_selection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора ставки для игры 1 на 1"""
    keyboard = [
        [InlineKeyboardButton("$1", callback_data="bet_1")],
        [InlineKeyboardButton("$5", callback_data="bet_5")],
        [InlineKeyboardButton("$10", callback_data="bet_10")],
        [InlineKeyboardButton("$25", callback_data="bet_25")],
        [InlineKeyboardButton("$50", callback_data="bet_50")],
        [InlineKeyboardButton("$100", callback_data="bet_100")],
        [InlineKeyboardButton("💵 Произвольная ставка", callback_data="custom_bet")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_game_creation")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_game_creator_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для создателя игры (после создания)"""
    keyboard = [
        [InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game_id}")],
        [InlineKeyboardButton("❌ Отменить игру", callback_data=f"cancel_active_game_{game_id}")],
        [InlineKeyboardButton("📋 Показать команду", callback_data=f"copy_{game_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_roll_again_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Кнопка для повторного броска"""
    keyboard = [
        [InlineKeyboardButton("🎲 Бросить снова", callback_data=f"roll_{game_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_roll_dice_keyboard(game_id: int) -> InlineKeyboardMarkup:
    """Кнопка для первого броска (присоединившийся игрок)"""
    keyboard = [
        [InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_waiting_keyboard() -> InlineKeyboardMarkup:
    """Кнопка ожидания (когда игрок завершил броски)"""
    keyboard = [
        [InlineKeyboardButton("⏳ Ожидаем соперника", callback_data="waiting")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    keyboard = [
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_custom_bet_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для запроса произвольной ставки"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Кнопка отмены создания игры"""
    keyboard = [
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_game_creation")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_game_invite_keyboard(game_code: str, bot_username: str) -> InlineKeyboardMarkup:
    """Клавиатура для приглашения в игру"""
    deep_link_url = f"https://t.me/{bot_username}?start=join_{game_code}"

    keyboard = [
        [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ", url=deep_link_url)],
        [InlineKeyboardButton("📋 Или используй команду", callback_data="show_command")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_game_result_keyboard(pay_url: str = None) -> InlineKeyboardMarkup:
    """Клавиатура с результатами игры"""
    buttons = []

    if pay_url:
        buttons.append([InlineKeyboardButton("💰 ПОЛУЧИТЬ ВЫИГРЫШ", url=pay_url)])

    buttons.append([InlineKeyboardButton("🎮 Новая игра", callback_data="find_game")])
    buttons.append([InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(buttons)


def get_deposit_keyboard(amount: float = None) -> InlineKeyboardMarkup:
    """Клавиатура для депозита"""
    keyboard = [
        [InlineKeyboardButton("$10", callback_data="deposit_10")],
        [InlineKeyboardButton("$25", callback_data="deposit_25")],
        [InlineKeyboardButton("$50", callback_data="deposit_50")],
        [InlineKeyboardButton("$100", callback_data="deposit_100")],
        [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_withdraw_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для вывода средств"""
    keyboard = [
        [InlineKeyboardButton("$10", callback_data="withdraw_10")],
        [InlineKeyboardButton("$25", callback_data="withdraw_25")],
        [InlineKeyboardButton("$50", callback_data="withdraw_50")],
        [InlineKeyboardButton("$100", callback_data="withdraw_100")],
        [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_withdraw")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


# Обновляем __init__.py в keyboards
# app/keyboards/__init__.py
"""
from .game_keyboards import (
    get_bet_selection_keyboard,
    get_game_creator_keyboard,
    get_roll_again_keyboard,
    get_roll_dice_keyboard,
    get_waiting_keyboard,
    get_back_to_menu_keyboard,
    get_custom_bet_keyboard,
    get_cancel_keyboard,
    get_game_invite_keyboard,
    get_game_result_keyboard,
    get_deposit_keyboard,
    get_withdraw_keyboard
)

__all__ = [
    'get_bet_selection_keyboard',
    'get_game_creator_keyboard',
    'get_roll_again_keyboard',
    'get_roll_dice_keyboard',
    'get_waiting_keyboard',
    'get_back_to_menu_keyboard',
    'get_custom_bet_keyboard',
    'get_cancel_keyboard',
    'get_game_invite_keyboard',
    'get_game_result_keyboard',
    'get_deposit_keyboard',
    'get_withdraw_keyboard'
]
"""