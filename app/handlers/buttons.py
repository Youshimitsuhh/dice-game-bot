# app/handlers/buttons.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
import logging

logger = logging.getLogger(__name__)


def register_button_handlers(application, bot):
    """Регистрируем обработчики inline-кнопок"""
    logger.info("🔘 Регистрируем обработчики кнопок")

    # Общий обработчик для большинства кнопок
    application.add_handler(CallbackQueryHandler(
        lambda update, context: button_handler(update, context, bot)
    ))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Основной обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"🔘 Нажата кнопка: '{data}' пользователем {user_id}")

    # ========== ВАЖНО: Пропускаем кнопки лобби ==========
    # Эти кнопки обрабатываются в lobby_handlers.py
    lobby_prefixes = ("lobby_bet_", "lobby_size_", "lobby_custom_bet",
                      "lobby_cancel", "lobby_toggle_ready:",
                      "lobby_start:", "lobby_leave:", "join_lobby:")

    if data.startswith(lobby_prefixes):
        logger.info(f"🔘 Кнопка лобби '{data}' передана в lobby_handlers")
        return  # Передаем управление в lobby_handlers.py

    # ========== ОБРАБОТКА ОСТАЛЬНЫХ КНОПОК ==========

    # Главное меню и навигация
    if data == "find_game":
        await show_bet_options(query, bot)


    elif data == "create_lobby_menu":

        await query.edit_message_text(

            "👥 **Создание лобби**\n\n"

            "Загрузка...",

            parse_mode='Markdown'

        )

    elif data == "stats":
        await show_stats(query, bot)

    elif data == "main_menu":
        await show_main_menu(query, bot)

    elif data == "help":
        await show_help(query, bot)

    elif data == "deposit":
        await show_deposit(query, bot)

    elif data == "withdraw":
        await show_withdraw(query, bot)

    # Игры 1 на 1
    elif data.startswith("bet_"):
        bet_amount = float(data.split("_")[1])
        await create_game(query, bet_amount, bot)

    elif data == "custom_bet":
        context.user_data['waiting_for_bet'] = True
        await ask_custom_bet(query, bot)

    elif data == "cancel_game_creation":
        await cancel_game_creation(query, bot)

    elif data.startswith("cancel_active_game_"):
        game_id = data.split("_")[3]
        await cancel_active_game(query, game_id, bot)

    elif data.startswith("roll_"):
        game_id = int(data.split("_")[1])
        await roll_dice(query, game_id, bot, context)

    elif data.startswith("copy_"):
        game_code = data.split("_")[1]
        await copy_command(query, game_code, bot)

    # Платежи
    elif data.startswith("deposit_"):
        amount = float(data.split("_")[1])
        await process_deposit(query, amount, bot)

    elif data == "custom_deposit":
        context.user_data['waiting_for_deposit'] = True
        await ask_custom_deposit(query, bot)

    elif data.startswith("withdraw_"):
        amount = float(data.split("_")[1])
        await process_withdraw(query, amount, bot)

    elif data == "custom_withdraw":
        context.user_data['waiting_for_withdraw'] = True
        await ask_custom_withdraw(query, bot)

    # Дуэли (пока заглушки)
    elif data.startswith("cancel_duel_"):
        chat_id = int(data.split("_")[2])
        await cancel_duel_in_chat(query, chat_id, bot)

    elif data.startswith("duel_"):
        # Дуэли будут обрабатываться в отдельном модуле
        logger.info(f"🔘 Кнопка дуэли '{data}' - будет обработана позже")
        await query.edit_message_text("⚔️ Дуэли в разработке...")

    else:
        logger.warning(f"❌ Неизвестная кнопка: {data}")
        await query.edit_message_text(f"❌ Неизвестная команда: {data}")


# ==================== ФУНКЦИИ ДЛЯ КНОПОК ====================

async def show_bet_options(query, bot):
    """Показывает выбор ставки для игры 1 на 1"""
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
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("🎯 Выберите сумму ставки:", reply_markup=reply_markup)


async def show_lobby_options(query, bot):
    """Показывает выбор ставки для лобби"""
    keyboard = [
        [InlineKeyboardButton("$1", callback_data="lobby_bet_1")],
        [InlineKeyboardButton("$5", callback_data="lobby_bet_5")],
        [InlineKeyboardButton("$10", callback_data="lobby_bet_10")],
        [InlineKeyboardButton("$25", callback_data="lobby_bet_25")],
        [InlineKeyboardButton("$50", callback_data="lobby_bet_50")],
        [InlineKeyboardButton("$100", callback_data="lobby_bet_100")],
        [InlineKeyboardButton("💵 Произвольная ставка", callback_data="lobby_custom_bet")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👥 **Создание мультиплеерного лобби**\n\n"
        "💰 Выберите сумму ставки для каждого игрока:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def create_game(query, bet_amount, bot):
    """Создает игру 1 на 1"""
    user_id = query.from_user.id
    user = bot.db.get_user(user_id)

    if not user:
        await query.edit_message_text("❌ Пользователь не найден")
        return

    current_balance = user[4]

    if current_balance < bet_amount:
        await query.edit_message_text(
            f"❌ Недостаточно средств!\n"
            f"Ваш баланс: ${current_balance:.0f}\n"
            f"Требуется: ${bet_amount:.0f}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                [InlineKeyboardButton("Назад", callback_data="find_game")]
            ])
        )
        return

    # TODO: Реализовать создание игры
    await query.edit_message_text(
        f"🎲 Создание игры на ${bet_amount:.0f}\n\n"
        "⚠️ Функция в разработке...\n"
        "Скоро будет доступно!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
    )


async def show_stats(query, bot):
    """Показывает статистику пользователя"""
    user_id = query.from_user.id
    stats = bot.db.get_user_stats(user_id)

    if stats:
        username, balance, games_played, games_won, win_rate = stats
        player_name = f"@{username}" if username else "Игрок"

        stats_text = (
            f"📊 Статистика {player_name}:\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            f"🎮 Игр сыграно: {games_played}\n"
            f"🏆 Побед: {games_won}\n"
            f"📈 Процент побед: {win_rate}%\n\n"
            f"💸 Комиссия системы: 8%"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(stats_text, reply_markup=reply_markup)


async def show_main_menu(query, bot):
    """Показывает главное меню"""
    user_id = query.from_user.id
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

    await query.edit_message_text(menu_text, reply_markup=reply_markup)


async def show_help(query, bot):
    """Показывает справку"""
    help_text = (
        "❓ Помощь по игре\n\n"
        "🎯 Как играть:\n"
        "1. Нажмите 'Создать игру'\n"
        "2. Выберите сумму ставки\n"
        "3. Другой игрок присоединяется по ID\n"
        "4. Бросайте кости\n"
        "5. Победитель забирает банк за вычетом комиссии 8%\n\n"
        "💸 Команды:\n"
        "/menu - открыть меню\n"
        "/deposit [сумма] - пополнить баланс\n"
        "/join [ID] - присоединиться к игре"
    )

    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(help_text, reply_markup=reply_markup)


async def show_deposit(query, bot):
    """Показывает варианты депозита"""
    keyboard = [
        [InlineKeyboardButton("$10", callback_data="deposit_10")],
        [InlineKeyboardButton("$25", callback_data="deposit_25")],
        [InlineKeyboardButton("$50", callback_data="deposit_50")],
        [InlineKeyboardButton("$100", callback_data="deposit_100")],
        [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text("💳 Выберите сумму для пополнения:", reply_markup=reply_markup)


async def show_withdraw(query, bot):
    """Показывает варианты вывода"""
    user_id = query.from_user.id
    user = bot.db.get_user(user_id)

    if user:
        balance = user[4]
        keyboard = [
            [InlineKeyboardButton("$10", callback_data="withdraw_10")],
            [InlineKeyboardButton("$25", callback_data="withdraw_25")],
            [InlineKeyboardButton("$50", callback_data="withdraw_50")],
            [InlineKeyboardButton("$100", callback_data="withdraw_100")],
            [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_withdraw")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"💸 Вывод средств\n\n"
            f"💰 Доступно: ${balance:.0f}\n"
            "Выберите сумму для вывода:",
            reply_markup=reply_markup
        )


async def process_deposit(query, amount, bot):
    """Обрабатывает депозит - заглушка"""
    await query.edit_message_text(
        f"💳 Депозит на ${amount:.0f}\n\n"
        "⚠️ Функция в разработке...\n"
        "Скоро будет доступно!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
    )


async def ask_custom_deposit(query, bot):
    """Запрашивает произвольную сумму депозита"""
    await query.edit_message_text(
        "💵 Введите сумму для пополнения (минимум $1):\n\n"
        "Пример: 15.5 или 75",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
        ])
    )


async def cancel_active_game(query, game_id, bot):
    """Отменяет активную игру - заглушка"""
    await query.edit_message_text(
        "✅ Игра отменена",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
    )

async def ask_custom_bet(query, bot):
    """Запрашиваем произвольную сумму ставки"""
    await query.edit_message_text(
        "💵 Введите сумму ставки (минимум $1):\n\n"
        "Пример: 15 или 75.5",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
        ])
    )

async def cancel_game_creation(query, bot):
    """Отмена создания новой игры"""
    await show_main_menu(query, bot)

async def roll_dice(query, game_id, bot, context):
    """Бросок костей - заглушка"""
    await query.edit_message_text(
        "🎲 Бросок костей\n\n"
        "⚠️ Функция в разработке...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
        ])
    )

async def copy_command(query, game_code, bot):
    """Показывает команду для копирования"""
    await query.edit_message_text(
        f"📋 **Команда для присоединения:**\n\n"
        f"`/join {game_code}`\n\n"
        "Просто скопируй и отправь другу!",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
        ])
    )

async def cancel_duel_in_chat(query, chat_id, bot):
    """Отмена дуэли в групповом чате - заглушка"""
    await query.edit_message_text(
        "⚔️ Отмена дуэли\n\n"
        "⚠️ Функция в разработке...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
        ])
    )