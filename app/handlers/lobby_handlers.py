# app/handlers/lobby_handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from datetime import datetime
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
        pattern=r"^(lobby_toggle_ready:|lobby_start:|lobby_leave:|join_lobby:|lobby_roll:)"
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

    if data.startswith("lobby_toggle_ready:"):
        # ОТЛАДКА
        logger.info(f"🔥 Нажата кнопка готовности: {data}")

        parts = data.split(":")
        if len(parts) < 3:
            await query.answer("❌ Неверный формат кнопки", show_alert=True)
            return

        lobby_id = parts[1]
        player_id = int(parts[2])

        # Проверяем что пользователь нажимает свою кнопку
        if user_id != player_id:
            await query.answer("❌ Вы можете менять только свой статус!", show_alert=True)
            return

        logger.info(f"🔄 Переключение готовности: lobby_id={lobby_id}, player_id={player_id}")

        await toggle_ready_callback(query, lobby_id, player_id, bot)
        return

    elif data.startswith("lobby_start:"):
        logger.info(f"🚀 Нажата кнопка начала игры: {data}")

        lobby_id = data.split(":")[1]
        await start_lobby_game(query, lobby_id, user_id, bot)

    elif data.startswith("lobby_leave:"):
        lobby_id = data.split(":")[1]
        await leave_lobby_callback(query, lobby_id, user_id, bot)

    elif data.startswith("join_lobby:"):
        lobby_id = data.split(":")[1]
        await join_lobby_callback(query, lobby_id, user_id, username, bot)

    elif data.startswith("lobby_roll:"):
        parts = data.split(":")
        game_id = parts[1]
        player_id = int(parts[2])
        await handle_lobby_roll(query, game_id, player_id, bot, context)

    else:
        logger.warning(f"⚠️ Неизвестный callback: {data}")
        await query.answer("❌ Эта кнопка пока не работает", show_alert=True)


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
        # Пытаемся отправить новое сообщение
        try:
            new_msg = await query.message.reply_text(text, reply_markup=keyboard, parse_mode='HTML')
            lobby.message_chat_id = new_msg.chat_id
            lobby.message_id = new_msg.message_id
        except:
            pass


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

    # Проверяем, не присоединился ли уже
    existing_player = lobby.get_player(user_id)
    if existing_player:
        await query.answer("✅ Вы уже в этом лобби!", show_alert=True)
        # Отправляем персональное сообщение игроку
        await send_personal_lobby_message(user_id, lobby, bot)
        return

    user = bot.db.get_user(user_id)
    if not user or user[4] < lobby.bet_amount:
        await query.answer(f"❌ Недостаточно средств! Нужно: ${lobby.bet_amount:.0f}",
                           show_alert=True)
        return

    # Присоединяемся
    success, message = bot.lobby_manager.join_lobby(lobby_id, user_id, username)

    if success:
        # Обновляем лобби (получаем свежую версию)
        lobby = bot.lobby_manager.get_lobby(lobby_id)

        # Списываем ставку
        bot.db.update_balance(user_id, -lobby.bet_amount)

        # Помечаем игрока как оплатившего
        player = lobby.get_player(user_id)
        if player:
            player.paid = True

        await query.answer(f"✅ Вы присоединились! Ставка ${lobby.bet_amount:.0f} списана.",
                           show_alert=True)

        # ОБНОВЛЯЕМ: Отправляем персональное сообщение игроку с кнопкой готовности
        await send_personal_lobby_message(user_id, lobby, bot)

        # Обновляем основное сообщение лобби (если есть)
        if hasattr(lobby, 'message_chat_id') and hasattr(lobby, 'message_id'):
            try:
                await send_lobby_message(query, lobby, bot)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления основного сообщения лобби: {e}")

        # Уведомляем создателя
        try:
            await bot.application.bot.send_message(
                chat_id=lobby.creator_id,
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!\n\n"
                     f"👥 Теперь игроков: {len(lobby.players)}/{lobby.max_players}"
            )
        except:
            pass

        # Отправляем создателю обновленное сообщение лобби
        try:
            if lobby.creator_id != user_id:  # Если присоединился не создатель
                await bot.application.bot.send_message(
                    chat_id=lobby.creator_id,
                    text=f"🔄 Лобби #{lobby_id} обновлено:\n\n"
                         f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n"
                         f"✅ Готовы: {sum(1 for p in lobby.players if p.ready)}/{len(lobby.players)}\n\n"
                         f"Когда все будут готовы, нажмите '▶️ Начать игру'",
                    reply_markup=get_lobby_keyboard(lobby)
                )
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления создателя: {e}")

    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def send_personal_lobby_message(user_id, lobby, bot):
    """Отправляет персональное сообщение с интерфейсом лобби игроку"""
    try:
        # Получаем информацию об игроке в лобби
        player = lobby.get_player(user_id)
        if not player:
            return

        player_status = "✅ Готов" if player.ready else "❌ Не готов"

        # Текст сообщения
        player_lobby_text = (
            f"🎮 **Вы в лобби!**\n\n"
            f"👤 Создатель: {lobby.creator_name}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n"
            f"✅ Готовы: {sum(1 for p in lobby.players if p.ready)}/{len(lobby.players)}\n"
            f"🆔 Код: `{lobby.id}`\n\n"
            f"📊 Ваш статус: {player_status}\n\n"
        )

        if lobby.status == "waiting":
            player_lobby_text += "🎯 **Действия:**\n"
            player_lobby_text += "1. Отметьте готовность, когда будете готовы играть\n"
            player_lobby_text += "2. Ожидайте, когда все игроки будут готовы\n"
            player_lobby_text += "3. Создатель начнет игру\n"
        elif lobby.status == "active":
            player_lobby_text += "🚀 **Игра уже началась!**\n"
            player_lobby_text += "Ожидайте своего хода..."

        # Клавиатура для игрока
        buttons = []

        if lobby.status == "waiting":
            # Кнопка переключения готовности
            ready_text = "✅ Я готов!" if not player.ready else "⏸ Я не готов"
            buttons.append([
                InlineKeyboardButton(
                    ready_text,
                    callback_data=f"lobby_toggle_ready:{lobby.id}:{user_id}"
                )
            ])

            # Кнопка выхода
            buttons.append([
                InlineKeyboardButton(
                    "❌ Выйти из лобби",
                    callback_data=f"lobby_leave:{lobby.id}"
                )
            ])

            # Кнопка "Начать игру" только для создателя
            if user_id == lobby.creator_id and lobby.all_players_ready():
                buttons.append([
                    InlineKeyboardButton(
                        "🚀 Начать игру",
                        callback_data=f"lobby_start:{lobby.id}"
                    )
                ])

        reply_markup = InlineKeyboardMarkup(buttons)

        # Отправляем сообщение
        await bot.application.bot.send_message(
            chat_id=user_id,
            text=player_lobby_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"❌ Ошибка отправки персонального сообщения игроку {user_id}: {e}")


async def toggle_ready_callback(query, lobby_id, player_id, bot):
    """Переключает статус готовности игрока - УПРОЩЕННАЯ ВЕРСИЯ"""

    logger.info(f"🔄 Начало toggle_ready_callback: lobby_id={lobby_id}, player_id={player_id}")

    # Получаем лобби
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        logger.error(f"❌ Лобби {lobby_id} не найдено")
        await query.answer("❌ Лобби не найдено", show_alert=True)
        return

    # Находим игрока
    player = lobby.get_player(player_id)
    if not player:
        logger.error(f"❌ Игрок {player_id} не найден в лобби")
        await query.answer("❌ Игрок не найден в лобби", show_alert=True)
        return

    logger.info(f"✅ Игрок найден: {player.username}, текущий статус: {player.ready}")

    # Меняем статус готовности
    player.ready = not player.ready
    logger.info(f"🔄 Новый статус игрока: {player.ready}")

    # Сохраняем в БД
    try:
        bot.lobby_manager.save_lobby_to_db(lobby)
        logger.info(f"💾 Лобби сохранено в БД")
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения лобби: {e}")

    # Обновляем сообщение лобби у всех игроков
    ready_count = sum(1 for p in lobby.players if p.ready)

    # 1. Обновляем сообщение у нажавшего игрока
    try:
        await send_personal_lobby_message(player_id, lobby, bot)
        logger.info(f"📨 Сообщение обновлено для игрока {player_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка обновления сообщения игрока: {e}")

    # 2. Обновляем сообщение у создателя (если это не создатель)
    if player_id != lobby.creator_id:
        try:
            await send_personal_lobby_message(lobby.creator_id, lobby, bot)
            logger.info(f"📨 Сообщение обновлено для создателя {lobby.creator_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка обновления сообщения создателя: {e}")

    # 3. Уведомление
    status = "готов" if player.ready else "не готов"
    await query.answer(f"✅ Вы теперь {status}")

    logger.info(f"✅ toggle_ready_callback завершено успешно")

    # Если все готовы - уведомляем создателя
    if lobby.all_players_ready() and lobby.is_full():
        try:
            await bot.application.bot.send_message(
                chat_id=lobby.creator_id,
                text=f"🎮 Все игроки в лобби #{lobby_id} готовы!\n"
                     f"Вы можете начать игру."
            )
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления создателя: {e}")


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
        print(f"💰 Возвращена ставка ${lobby.bet_amount} игроку {user_id}")

    # Выходим из лобби
    success, message = bot.lobby_manager.leave_lobby(lobby_id, user_id)

    if success:
        # Сохраняем изменения
        if "удалено" not in message:
            bot.lobby_manager.save_lobby_to_db(lobby)

        await query.answer("✅ Вы вышли из лобби", show_alert=True)

        if "удалено" in message:
            # Лобби удалено
            await query.edit_message_text("🗑 Лобби удалено (все игроки вышли)")
        else:
            # Обновляем сообщение если лобби еще существует
            lobby = bot.lobby_manager.get_lobby(lobby_id)
            if lobby:
                await send_lobby_message(query, lobby, bot)
            else:
                await query.edit_message_text("❌ Лобби больше не существует")
    else:
        await query.answer(f"❌ {message}", show_alert=True)


async def start_lobby_game(query, lobby_id, user_id, bot):
    """Запускает игру в лобби"""
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

    # Проверяем минимальное количество игроков
    if len(lobby.players) < 2:
        await query.answer("❌ Нужно минимум 2 игрока для начала игры", show_alert=True)
        return

    logger.info(f"🚀 Создатель {user_id} начинает игру в лобби {lobby_id}")

    # Меняем статус лобби
    lobby.status = "active"
    bot.lobby_manager.save_lobby_to_db(lobby)

    # Создаем структуру игры - ИСПОЛЬЗУЕМ active_lobby_games
    game_id = f"lobby_{lobby_id}"

    # Убедимся что bot имеет атрибут active_lobby_games
    if not hasattr(bot, 'active_lobby_games'):
        logger.warning("⚠️ bot не имеет active_lobby_games, создаем...")
        bot.active_lobby_games = {}

    bot.active_lobby_games[game_id] = {
        "lobby_id": lobby_id,
        "players": lobby.players,
        "current_player_index": 0,
        "rolls": {p.id: [] for p in lobby.players},
        "max_rolls": 3,
        "status": "active",
        "bet_amount": lobby.bet_amount,
        "created_at": datetime.now().isoformat()
    }

    logger.info(f"🎮 Создана лобби-игра {game_id} с {len(lobby.players)} игроками")

    # Уведомляем всех игроков
    player_list = "\n".join([f"👤 {p.username}" for p in lobby.players])
    first_player = lobby.players[0]

    game_message = (
        f"🚀 **Игра началась!**\n\n"
        f"🎲 Лобби #{lobby.id}\n"
        f"💰 Ставка: ${lobby.bet_amount:.0f} с игрока\n"
        f"🏦 Общий банк: ${lobby.bet_amount * len(lobby.players):.0f}\n\n"
        f"👥 Игроки:\n{player_list}\n\n"
        f"🎯 Первый ход: **{first_player.username}**\n"
        f"🎲 Каждый игрок делает 3 броска"
    )

    # Кнопка для первого игрока
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎲 Бросить кости",
                             callback_data=f"lobby_roll:{game_id}:{first_player.id}")
    ]])

    # Отправляем сообщение в чат создателя
    try:
        await query.edit_message_text(game_message, reply_markup=keyboard, parse_mode='Markdown')
        logger.info(f"📨 Сообщение об игре отправлено создателю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка редактирования сообщения: {e}")
        # Пытаемся отправить новое сообщение
        try:
            await query.message.reply_text(game_message, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e2:
            logger.error(f"❌ Ошибка отправки нового сообщения: {e2}")

    # Отправляем уведомления остальным игрокам
    for player in lobby.players:
        # Пропускаем создателя (ему уже отправили)
        if player.id == user_id:
            continue

        try:
            player_message = (
                f"🎮 **Игра в лобби #{lobby.id} началась!**\n\n"
                f"💰 Ваша ставка: ${lobby.bet_amount:.0f}\n"
                f"👥 Игроков: {len(lobby.players)}\n"
                f"🏦 Общий банк: ${lobby.bet_amount * len(lobby.players):.0f}\n\n"
                f"🎯 Первый ход: {first_player.username}\n"
                f"⏳ Ожидайте своего хода..."
            )

            await bot.application.bot.send_message(
                chat_id=player.id,
                text=player_message,
                parse_mode='Markdown'
            )
            logger.info(f"📨 Уведомление отправлено игроку {player.id}")

        except Exception as e:
            logger.error(f"❌ Ошибка уведомления игрока {player.id}: {e}")


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
        status_emoji = "✅" if player.ready else "❌"
        buttons.append([
            InlineKeyboardButton(
                f"{status_emoji} {player.username}",
                callback_data=f"lobby_toggle_ready:{lobby.id}:{player.id}"
            )
        ])

    # Кнопка "Начать игру" для создателя (показывается всем если все готовы)
    ready_count = sum(1 for p in lobby.players if p.ready)
    if ready_count == len(lobby.players) and len(lobby.players) >= 2:
        buttons.append([
            InlineKeyboardButton("🚀 НАЧАТЬ ИГРУ", callback_data=f"lobby_start:{lobby.id}")
        ])
    else:
        # Показываем статус готовности
        buttons.append([
            InlineKeyboardButton(
                f"⏳ Готовы: {ready_count}/{len(lobby.players)}",
                callback_data="refresh_lobby"
            )
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


async def handle_lobby_roll(query, game_id, player_id, bot, context):
    """Обработчик броска костей в лобби"""
    # Проверяем что пользователь - тот кто должен бросать
    if query.from_user.id != player_id:
        await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return

    # Используем active_lobby_games
    game = bot.active_lobby_games.get(game_id) if hasattr(bot, 'active_lobby_games') else None
    if not game:
        await query.answer("❌ Игра не найдена", show_alert=True)
        return

    lobby = bot.lobby_manager.get_lobby(game["lobby_id"])
    if not lobby:
        await query.answer("❌ Лобби не найдено", show_alert=True)
        return

    # Проверяем чей сейчас ход
    current_player = game["players"][game["current_player_index"]]
    if current_player.id != player_id:
        await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
        return

    # Бросаем кости
    dice_message = await query.message.reply_dice(emoji="🎲")
    dice_value = dice_message.dice.value

    # Ждем анимацию
    await asyncio.sleep(3)

    # Сохраняем бросок
    if player_id not in game["rolls"]:
        game["rolls"][player_id] = []
    game["rolls"][player_id].append(dice_value)
    rolls_count = len(game["rolls"][player_id])

    # Получаем имя игрока
    player_name = next((p.username for p in lobby.players if p.id == player_id), "Игрок")

    # Формируем сообщение
    roll_message = (
        f"🎲 {player_name} бросает кости!\n\n"
        f"🎯 Выпало: {dice_value}\n"
        f"📊 Бросок {rolls_count}/{game['max_rolls']}\n"
    )

    # Показываем текущие результаты
    results = []
    for player in lobby.players:
        player_rolls = game["rolls"].get(player.id, [])
        total = sum(player_rolls)
        rolls_str = ", ".join(map(str, player_rolls)) if player_rolls else "—"
        results.append(f"👤 {player.username}: {rolls_str} (Сумма: {total})")

    if results:
        roll_message += "\n📈 Текущие результаты:\n" + "\n".join(results)

    # Проверяем завершил ли игрок свои броски
    if rolls_count >= game["max_rolls"]:
        # Игрок завершил все броски
        roll_message += f"\n\n✅ {player_name} завершил все броски!"

        # Переходим к следующему игроку
        game["current_player_index"] += 1
        logger.info(f"🔄 Текущий индекс игрока: {game['current_player_index']}, всего игроков: {len(game['players'])}")

        if game["current_player_index"] < len(game["players"]):
            next_player = game["players"][game["current_player_index"]]
            roll_message += f"\n\n➡️ Следующий ход: **{next_player.username}**"

            # Кнопка для следующего игрока
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Бросить кости",
                                     callback_data=f"lobby_roll:{game_id}:{next_player.id}")
            ]])

            await query.message.reply_text(roll_message, reply_markup=keyboard, parse_mode='Markdown')

            # Также отправляем уведомление следующему игроку
            try:
                await bot.application.bot.send_message(
                    chat_id=next_player.id,
                    text=f"🎮 **Ваш ход в лобби #{lobby.id}!**\n\n"
                         f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
                         f"👥 Игроков: {len(lobby.players)}\n\n"
                         f"🎲 Нажмите кнопку ниже, чтобы бросить кости:",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"❌ Ошибка уведомления следующего игрока: {e}")

        else:
            # Все игроки завершили броски
            roll_message += "\n\n🏁 **Все игроки завершили броски!**\nПодсчитываем результаты..."
            await query.message.reply_text(roll_message, parse_mode='Markdown')

            # Завершаем игру
            await finish_lobby_game(game_id, lobby, bot)
    else:
        # У игрока еще есть броски
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 Бросить снова",
                                 callback_data=f"lobby_roll:{game_id}:{player_id}")
        ]])

        await query.message.reply_text(roll_message, reply_markup=keyboard, parse_mode='Markdown')


async def finish_lobby_game(game_id, lobby, bot):
    """Завершает игру в лобби и определяет победителя"""
    # Используем active_lobby_games вместо games
    game = bot.active_lobby_games.get(game_id) if hasattr(bot, 'active_lobby_games') else None
    if not game:
        logger.error(f"❌ Игра {game_id} не найдена в active_lobby_games")
        return

    # Вычисляем результаты
    results = []
    for player in lobby.players:
        player_rolls = game["rolls"].get(player.id, [])
        total = sum(player_rolls)
        results.append({
            "player": player,
            "total": total,
            "rolls": player_rolls
        })

    # Сортируем по убыванию суммы
    results.sort(key=lambda x: x["total"], reverse=True)

    # Проверяем на ничью
    if len(results) > 1 and results[0]["total"] == results[1]["total"]:
        # Ничья - возвращаем деньги
        for player in lobby.players:
            bot.db.update_balance(player.id, lobby.bet_amount)
            logger.info(f"💰 Возвращена ставка ${lobby.bet_amount:.0f} игроку {player.id} (ничья)")

        # Сообщение о ничье
        results_text = "\n".join([f"👤 {r['player'].username}: Сумма {r['total']} ({', '.join(map(str, r['rolls']))})"
                                  for r in results])

        winner_message = (
            f"🤝 **НИЧЬЯ!**\n\n"
            f"🎲 Лобби #{lobby.id}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f} с игрока\n"
            f"👥 Игроков: {len(lobby.players)}\n\n"
            f"📊 Результаты:\n{results_text}\n\n"
            f"💰 Ставки возвращены всем игрокам"
        )

    else:
        # Есть победитель
        winner = results[0]["player"]
        total_bank = lobby.bet_amount * len(lobby.players)
        winner_prize = total_bank * 0.92  # 8% комиссия
        commission = total_bank * 0.08

        # Начисляем выигрыш
        bot.db.update_balance(winner.id, winner_prize)
        logger.info(f"🏆 Победитель {winner.id} получает ${winner_prize:.0f} (комиссия: ${commission:.0f})")

        # Формируем сообщение
        results_text = "\n".join(
            [f"{i + 1}. 👤 {r['player'].username}: Сумма {r['total']} ({', '.join(map(str, r['rolls']))})"
             for i, r in enumerate(results)])

        winner_message = (
            f"🏆 **ПОБЕДИТЕЛЬ: {winner.username}!**\n\n"
            f"🎲 Лобби #{lobby.id}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f} с игрока\n"
            f"👥 Игроков: {len(lobby.players)}\n"
            f"🏦 Общий банк: ${total_bank:.0f}\n"
            f"💸 Выигрыш: ${winner_prize:.0f} (комиссия 8%: ${commission:.0f})\n\n"
            f"📊 Результаты:\n{results_text}"
        )

        # Отправляем персональное сообщение победителю
        try:
            await bot.application.bot.send_message(
                chat_id=winner.id,
                text=f"🎉 **ПОЗДРАВЛЯЕМ С ПОБЕДОЙ!**\n\n"
                     f"🏆 Вы победили в лобби #{lobby.id}\n"
                     f"💰 Ваш выигрыш: ${winner_prize:.0f}\n"
                     f"💳 Баланс зачислен!",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения победителю {winner.id}: {e}")

    # Отправляем результат всем игрокам в лобби
    for player in lobby.players:
        try:
            # Не отправляем победителю повторно (ему уже отправили)
            if 'winner' in locals() and player.id == winner.id:
                continue

            await bot.application.bot.send_message(
                chat_id=player.id,
                text=winner_message,
                parse_mode='Markdown'
            )
            logger.info(f"📨 Результат отправлен игроку {player.id}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки результата игроку {player.id}: {e}")

    # Также отправляем в чат создателя (основной чат)
    try:
        if hasattr(lobby, 'message_chat_id'):
            await bot.application.bot.send_message(
                chat_id=lobby.message_chat_id,
                text=winner_message,
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"❌ Ошибка отправки результата в чат создателя: {e}")

    # Удаляем лобби из менеджера
    try:
        bot.lobby_manager.delete_lobby(lobby.id)
        logger.info(f"🗑️ Лобби {lobby.id} удалено")
    except Exception as e:
        logger.error(f"❌ Ошибка удаления лобби: {e}")

    # Удаляем игру из active_lobby_games
    if hasattr(bot, 'active_lobby_games') and game_id in bot.active_lobby_games:
        del bot.active_lobby_games[game_id]
        logger.info(f"🗑️ Лобби-игра {game_id} удалена из активных игр")
    else:
        logger.warning(f"⚠️ Игра {game_id} не найдена в active_lobby_games для удаления")