# app/handlers/messages.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters
import logging

logger = logging.getLogger(__name__)


def register_message_handlers(application, bot):
    """Регистрируем обработчики текстовых сообщений"""
    logger.info("💬 Регистрируем обработчики сообщений")

    # Обработчик текстовых сообщений (не команд)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        lambda update, context: handle_message(update, context, bot)
    ))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик текстовых сообщений"""
    chat = update.effective_chat
    user_id = update.effective_user.id
    message_text = update.message.text.strip()

    logger.info(f"💬 Сообщение от {user_id}: '{message_text[:50]}...' в чате {chat.type}")

    # ────────── ГРУППЫ ──────────
    if chat.type in ["group", "supergroup"]:
        # В группах обрабатываем только числовые вводы для ожидаемых действий
        if not (context.user_data.get('waiting_for_bet') or
                context.user_data.get('waiting_for_deposit') or
                context.user_data.get('waiting_for_withdraw')):
            return  # Игнорируем все сообщения в группах

    # ────────── ПРИВАТНЫЙ ЧАТ ──────────

    # 1. Ожидаем ввод ставки для ОБЫЧНОЙ игры
    if context.user_data.get('waiting_for_bet'):
        context.user_data['waiting_for_bet'] = False
        await handle_bet_input(update, message_text, bot)
        return

    # 2. Ожидаем ввод ставки для ЛОББИ
    elif context.user_data.get('waiting_for_lobby_bet'):
        context.user_data['waiting_for_lobby_bet'] = False
        await handle_lobby_bet_input(update, message_text, bot)
        return

    # 3. Ожидаем ввод депозита
    elif context.user_data.get('waiting_for_deposit'):
        context.user_data['waiting_for_deposit'] = False
        await handle_deposit_input(update, message_text, bot)
        return

    # 4. Ожидаем ввод вывода
    elif context.user_data.get('waiting_for_withdraw'):
        context.user_data['waiting_for_withdraw'] = False
        await handle_withdraw_input(update, message_text, bot)
        return

    # Если сообщение не число - показываем меню (только в приватном чате)
    if chat.type == "private":
        try:
            float(message_text)
            await update.message.reply_text(
                "💡 Вы ввели число, но не выбрали действие.\n\n"
                "Используйте меню (/menu)."
            )
        except ValueError:
            # Только если это не команда
            if not message_text.startswith('/'):
                await show_menu_from_message(update, bot)


async def handle_bet_input(update, message_text, bot):
    """Обрабатывает ввод ставки для обычной игры"""
    try:
        bet_amount = float(message_text)
        if bet_amount < 1:
            await update.message.reply_text("❌ Минимальная ставка $1")
            return

        # TODO: Реализовать создание игры
        await update.message.reply_text(
            f"🎲 Ставка: ${bet_amount:.0f}\n\n"
            "⚠️ Создание игры в разработке...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
            ])
        )

    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму (например: 25 или 50.5)")


async def handle_lobby_bet_input(update, message_text, bot):
    """Обрабатывает ввод ставки для лобби"""
    try:
        bet_amount = float(message_text)
        if bet_amount < 1:
            await update.message.reply_text("❌ Минимальная ставка $1")
            return

        # Показываем выбор количества игроков
        keyboard = [
            [InlineKeyboardButton("👥 3 игрока", callback_data=f"lobby_size_{bet_amount}_3")],
            [InlineKeyboardButton("👥 4 игрока", callback_data=f"lobby_size_{bet_amount}_4")],
            [InlineKeyboardButton("👥 5 игроков", callback_data=f"lobby_size_{bet_amount}_5")],
            [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👥 **Создание лобби**\n\n"
            f"💰 Ставка: **${bet_amount:.0f}** с игрока\n\n"
            "Выберите количество игроков:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму (например: 25 или 50.5)")


async def handle_deposit_input(update, message_text, bot):
    """Обрабатывает ввод суммы депозита"""
    try:
        amount = float(message_text)
        if amount < 1:
            await update.message.reply_text("❌ Минимальная сумма $1")
            return

        # TODO: Реализовать депозит
        await update.message.reply_text(
            f"💳 Депозит на ${amount:.0f}\n\n"
            "⚠️ Функция в разработке...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
            ])
        )

    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму")


async def handle_withdraw_input(update, message_text, bot):
    """Обрабатывает ввод суммы вывода"""
    try:
        amount = float(message_text)

        # TODO: Реализовать вывод
        await update.message.reply_text(
            f"💸 Вывод ${amount:.0f}\n\n"
            "⚠️ Функция в разработке...",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
            ])
        )

    except ValueError:
        await update.message.reply_text("❌ Введите корректную сумму")


async def show_menu_from_message(update, bot):
    """Показывает меню из текстового сообщения"""
    user_id = update.effective_user.id
    stats = bot.db.get_user_stats(user_id)
    balance = stats[1] if stats else 0

    menu_text = (
        f"🎲 Главное меню\n\n"
        f"💰 Баланс: ${balance:.0f}\n"
        "Выберите действие:"
    )

    keyboard = [
        [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
        [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
         InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(menu_text, reply_markup=reply_markup)