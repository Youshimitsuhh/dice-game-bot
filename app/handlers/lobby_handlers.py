# app/handlers/lobby_handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
import logging
import asyncio

from app.models.lobby import LobbyPlayer

logger = logging.getLogger(__name__)


def register_lobby_handlers(application, bot):
    """Регистрируем обработчики лобби"""
    logger.info("🎮 Регистрируем обработчики лобби")

    # Обработчики для кнопок создания лобби
    application.add_handler(CallbackQueryHandler(
        lambda update, context: handle_lobby_callback(update, context, bot),
        pattern=r"^(lobby_bet_|lobby_size_|lobby_custom_bet|lobby_cancel|create_lobby_menu)"
    ))

    # Обработчики действий в лобби
    application.add_handler(CallbackQueryHandler(
        lambda update, context: handle_lobby_actions(update, context, bot),
        pattern=r"^(lobby_toggle_ready:|lobby_start:|lobby_leave:|join_lobby:)"
    ))


async def handle_lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик кнопок создания лобби"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"🎮 Кнопка лобби: '{data}' от {user_id}")

    if data == "create_lobby_menu":
        await show_lobby_menu(query, bot)
        return

    if data == "lobby_cancel":
        await show_main_menu(query, bot)
        return

    elif data.startswith("lobby_bet_"):
        # Кнопка выбора ставки: lobby_bet_10
        bet_amount = float(data.split("_")[2])
        await show_lobby_size_options(query, bet_amount, bot)

    elif data == "lobby_custom_bet":
        # Запрос произвольной ставки
        context.user_data['waiting_for_lobby_bet'] = True
        await ask_custom_lobby_bet(query, bot)

    elif data.startswith("lobby_size_"):
        # Кнопка выбора количества игроков: lobby_size_10_3
        parts = data.split("_")
        bet_amount = float(parts[2])
        max_players = int(parts[3])
        await create_lobby_with_bet(query, bet_amount, max_players, bot)


async def handle_lobby_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик действий внутри лобби"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name

    logger.info(f"🎮 Действие в лобби: '{data}' от {username}")

    if data.startswith("join_lobby:"):
        # Присоединение к лобби
        lobby_id = data.split(":")[1]
        await join_lobby_callback(query, lobby_id, user_id, username, bot)

    elif data.startswith("lobby_toggle_ready:"):
        # Переключение готовности
        parts = data.split(":")
        lobby_id = parts[1]
        player_id = int(parts[2])
        await toggle_ready_callback(query, lobby_id, player_id, bot)

    elif data.startswith("lobby_leave:"):
        # Выход из лобби
        lobby_id = data.split(":")[1]
        await leave_lobby_callback(query, lobby_id, user_id, bot)

    elif data.startswith("lobby_start:"):
        # Запуск игры в лобби
        lobby_id = data.split(":")[1]
        await start_lobby_game(query, lobby_id, user_id, bot)


# ==================== ФУНКЦИИ ДЛЯ ЛОББИ ====================

async def show_lobby_size_options(query, bet_amount, bot):
    """Показывает выбор количества игроков для лобби"""
    keyboard = [
        [InlineKeyboardButton("👥 3 игрока", callback_data=f"lobby_size_{bet_amount}_3")],
        [InlineKeyboardButton("👥 4 игрока", callback_data=f"lobby_size_{bet_amount}_4")],
        [InlineKeyboardButton("👥 5 игроков", callback_data=f"lobby_size_{bet_amount}_5")],
        [InlineKeyboardButton("🔙 Назад к ставке", callback_data="create_lobby_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"👥 **Создание лобби**\n\n"
        f"💰 Ставка: **${bet_amount:.0f}** с игрока\n\n"
        "Выберите количество игроков:\n"
        "• 3 игрока - быстрые игры\n"
        "• 4 игрока - оптимальный вариант\n"
        "• 5 игроков - масштабные баталии\n\n"
        f"💰 **Общий банк:** ${bet_amount * 3:.0f}-${bet_amount * 5:.0f}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def ask_custom_lobby_bet(query, bot):
    """Запрашивает произвольную сумму ставки для лобби"""
    await query.edit_message_text(
        "💵 Введите сумму ставки для каждого игрока (минимум $1):\n\n"
        "Пример: 15 или 75.5\n\n"
        "💰 Каждый игрок будет вносить эту сумму",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
        ])
    )


async def create_lobby_with_bet(query, bet_amount, max_players, bot):
    """Создает лобби с указанной ставкой"""
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name

    logger.info(f"🎲 Создание лобби: ставка ${bet_amount}, игроков: {max_players}")

    # Проверяем баланс
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
                [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
            ])
        )
        return

    # Списываем ставку
    bot.db.update_balance(user_id, -bet_amount)

    # Создаем лобби через менеджер
    lobby = bot.lobby_manager.create_lobby(
        creator_id=user_id,
        creator_name=username,
        bet_amount=bet_amount,
        max_players=max_players
    )

    # Сохраняем ID сообщения
    lobby.message_chat_id = query.message.chat.id
    lobby.message_id = query.message.message_id

    # Отправляем сообщение лобби
    await send_lobby_message(query, lobby, bot)

    # Отправляем приглашение
    await send_lobby_invite(query, lobby, bot)

    await query.edit_message_text(
        f"✅ Лобби создано!\n\n"
        f"💰 Ставка: ${bet_amount:.0f} с игрока\n"
        f"👥 Игроков: 1/{max_players}\n"
        f"🆔 Код: {lobby.id}\n\n"
        f"📤 Отправьте приглашение друзьям!",
        parse_mode='Markdown'
    )


async def send_lobby_message(query, lobby, bot):
    """Отправляет/обновляет сообщение лобби"""
    text = lobby.get_lobby_text()
    keyboard = get_lobby_keyboard(lobby)

    try:
        await bot.application.bot.edit_message_text(
            chat_id=lobby.message_chat_id,
            message_id=lobby.message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения лобби: {e}")


async def send_lobby_invite(query, lobby, bot):
    """Отправляет приглашение в лобби"""
    try:
        bot_info = await bot.application.bot.get_me()
        bot_username = bot_info.username

        deep_link_url = f"https://t.me/{bot_username}?start=joinlobby_{lobby.id}"
        total_bank = lobby.bet_amount * lobby.max_players

        invite_text = (
            f"🎮 **Приглашение в лобби!**\n\n"
            f"👤 Создатель: {lobby.creator_name}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f} с игрока\n"
            f"🏦 Общий банк: ${total_bank:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n"
            f"🆔 Код: `{lobby.id}`\n\n"
            f"🎯 [Присоединиться]({deep_link_url})"
        )

        await query.message.reply_text(
            invite_text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.error(f"❌ Ошибка отправки приглашения: {e}")
        # Запасной вариант
        await query.message.reply_text(
            f"🎮 Приглашение в лобби!\n\n"
            f"👤 Создатель: {lobby.creator_name}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n"
            f"🆔 Код: {lobby.id}\n\n"
            f"Используйте: /join_lobby {lobby.id}"
        )


async def join_lobby_callback(query, lobby_id, user_id, username, bot):
    """Обработчик присоединения к лобби"""
    # Проверяем баланс
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        await query.answer("❌ Лобби не найдено", show_alert=True)
        return

    user = bot.db.get_user(user_id)
    if not user or user[4] < lobby.bet_amount:
        await query.answer(f"❌ Недостаточно средств! Нужно: ${lobby.bet_amount:.0f}",
                           show_alert=True)
        return

    # Присоединяемся
    success, message = bot.lobby_manager.join_lobby(lobby_id, user_id, username)

    if success:
        # Списываем ставку
        bot.db.update_balance(user_id, -lobby.bet_amount)

        # Помечаем игрока как оплатившего
        player = lobby.get_player(user_id)
        if player:
            player.paid = True

        await query.answer(f"✅ Вы присоединились! Ставка ${lobby.bet_amount:.0f} списана.",
                           show_alert=True)

        # Обновляем сообщение лобби
        await send_lobby_message(query, lobby, bot)

        # Уведомляем создателя
        try:
            await bot.application.bot.send_message(
                chat_id=lobby.creator_id,
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!"
            )
        except:
            pass
    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def toggle_ready_callback(query, lobby_id, player_id, bot):
    """Переключает статус готовности игрока"""
    success, message = bot.lobby_manager.toggle_ready(lobby_id, player_id)

    if success:
        lobby = bot.lobby_manager.get_lobby(lobby_id)

        # Если все готовы - запускаем таймер
        if lobby and lobby.all_players_ready() and not lobby.timer_started:
            # Запускаем таймер в фоне
            asyncio.create_task(
                bot.lobby_manager.start_lobby_timer(
                    lobby_id,
                    lambda lid: start_lobby_game_auto(lid, bot),
                    timeout=30
                )
            )

        # Обновляем сообщение
        await send_lobby_message(query, lobby, bot)
    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def leave_lobby_callback(query, lobby_id, user_id, bot):
    """Игрок выходит из лобби"""
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        await query.answer("❌ Лобби не найдено", show_alert=True)
        return

    # Возвращаем ставку если игрок оплатил
    player = lobby.get_player(user_id)
    if player and player.paid:
        bot.db.update_balance(user_id, lobby.bet_amount)

    # Выходим из лобби
    success, message = bot.lobby_manager.leave_lobby(lobby_id, user_id)

    if success:
        await query.answer("✅ Вы вышли из лобби", show_alert=True)

        if "удалено" in message:
            await query.edit_message_text("🗑 Лобби удалено (все игроки вышли)")
        else:
            # Обновляем сообщение если лобби еще существует
            lobby = bot.lobby_manager.get_lobby(lobby_id)
            if lobby:
                await send_lobby_message(query, lobby, bot)
    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def start_lobby_game(query, lobby_id, user_id, bot):
    """Запускает игру в лобби (по нажатию кнопки)"""
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        await query.answer("❌ Лобби не найдено", show_alert=True)
        return

    # Проверяем права
    if user_id != lobby.creator_id:
        await query.answer("❌ Только создатель может начать игру", show_alert=True)
        return

    # Проверяем что все готовы и лобби заполнено
    if not lobby.all_players_ready():
        await query.answer("❌ Не все игроки готовы", show_alert=True)
        return

    # Запускаем игру
    await query.edit_message_text("🎮 Запускаем игру...")
    # TODO: Реализовать запуск игры


async def start_lobby_game_auto(lobby_id, bot):
    """Автоматический запуск игры по таймеру"""
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        return

    logger.info(f"🚀 Автозапуск игры в лобби {lobby_id}")

    try:
        await bot.application.bot.edit_message_text(
            chat_id=lobby.message_chat_id,
            message_id=lobby.message_id,
            text=f"🚀 Игра в лобби #{lobby_id} началась!\n\n"
                 f"👥 Игроков: {len(lobby.players)}\n"
                 f"💰 Ставка: ${lobby.bet_amount:.0f} с игрока",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"❌ Ошибка автозапуска: {e}")


def get_lobby_keyboard(lobby):
    """Создает клавиатуру для сообщения лобби"""
    buttons = []

    # Кнопки готовности для каждого игрока
    for player in lobby.players:
        text = "Не готов" if player.ready else "Готов"
        buttons.append([
            InlineKeyboardButton(
                f"{text} ({player.username})",
                callback_data=f"lobby_toggle_ready:{lobby.id}:{player.id}"
            )
        ])

    # Кнопка "Начать игру" для создателя
    if lobby.all_players_ready() and lobby.creator_id in [p.id for p in lobby.players]:
        buttons.append([
            InlineKeyboardButton("▶️ Начать игру", callback_data=f"lobby_start:{lobby.id}")
        ])

    # Кнопка присоединиться (если есть места)
    if not lobby.is_full():
        buttons.append([
            InlineKeyboardButton("🎮 Присоединиться", callback_data=f"join_lobby:{lobby.id}")
        ])

    # Кнопка выйти
    buttons.append([
        InlineKeyboardButton("❌ Выйти из лобби", callback_data=f"lobby_leave:{lobby.id}")
    ])

    return InlineKeyboardMarkup(buttons)


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

async def show_lobby_options(query, bot):
    """Показывает выбор ставки для лобби - теперь перенаправляет"""
    # Эта кнопка теперь обрабатывается в lobby_handlers
    # Но на всякий случай оставляем заглушку
    await query.edit_message_text(
        "👥 **Создание мультиплеерного лобби**\n\n"
        "Переадресация...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 Открыть создание лобби",
                                  callback_data="create_lobby_menu")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]),
        parse_mode='Markdown'
    )


async def show_lobby_menu(query, bot):
    """Показывает меню создания лобби"""
    user_id = query.from_user.id
    user = bot.db.get_user(user_id)

    if not user:
        await query.edit_message_text("❌ Пользователь не найден")
        return

    balance = user[4]

    menu_text = (
        f"👥 **Создание мультиплеерного лобби**\n\n"
        f"💰 Ваш баланс: ${balance:.0f}\n"
        "Выберите сумму ставки для каждого игрока:"
    )

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

    await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_lobby_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик кнопок создания лобби"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"🎮 Кнопка лобби: '{data}' от {user_id}")

    if data == "create_lobby_menu":
        await show_lobby_menu(query, bot)
        return

    elif data == "lobby_cancel":
        await show_main_menu(query, bot)
        return

    elif data.startswith("lobby_bet_"):
        # Кнопка выбора ставки: lobby_bet_10
        bet_amount = float(data.split("_")[2])
        await show_lobby_size_options(query, bet_amount, bot)

    elif data == "lobby_custom_bet":
        # Запрос произвольной ставки
        context.user_data['waiting_for_lobby_bet'] = True
        await ask_custom_lobby_bet(query, bot)

    elif data.startswith("lobby_size_"):
        # Кнопка выбора количества игроков: lobby_size_10_3
        parts = data.split("_")
        bet_amount = float(parts[2])
        max_players = int(parts[3])
        await create_lobby_with_bet(query, bet_amount, max_players, bot)