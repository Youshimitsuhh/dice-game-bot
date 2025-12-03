# app/handlers/commands.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
import logging
from app.handlers.lobby_handlers import get_lobby_keyboard

logger = logging.getLogger(__name__)


def register_command_handlers(application, bot):
    """Регистрируем обработчики команд"""
    logger.info("📝 Регистрируем обработчики команд")

    application.add_handler(CommandHandler("start",
                                           lambda update, context: start_command(update, context, bot)))
    application.add_handler(CommandHandler("menu",
                                           lambda update, context: menu_command(update, context, bot)))
    application.add_handler(CommandHandler("help",
                                           lambda update, context: help_command(update, context, bot)))
    application.add_handler(CommandHandler("deposit",
                                           lambda update, context: deposit_command(update, context, bot)))
    application.add_handler(CommandHandler("join",
                                           lambda update, context: join_command(update, context, bot)))
    application.add_handler(CommandHandler("create",
                                           lambda update, context: create_lobby_command(update, context, bot)))
    application.add_handler(CommandHandler("duel",
                                           lambda update, context: duel_command(update, context, bot)))
    application.add_handler(CommandHandler("join_lobby",
                                           lambda update, context: join_lobby_command(update, context, bot)))


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик команды /start с поддержкой глубоких ссылок"""
    user = update.effective_user
    chat = update.effective_chat

    logger.info(f"👤 /start от {user.id} ({user.username}) в чате {chat.type}")
    logger.info(f"📦 Аргументы: {context.args}")

    # Блокируем старт в групповых чатах
    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "🎯 Для игры в кости используйте команды:\n\n"
            "/duel <ставка> - создать дуэль\n"
            "/join <код> - присоединиться к игре\n\n"
            "📱 Для пополнения баланса и настроек перейдите в личный чат с ботом."
        )
        return

    # Регистрируем пользователя
    bot.db.register_user(user.id, user.username, user.first_name)

    # ========== ОБРАБОТКА ГЛУБОКИХ ССЫЛОК ==========

    # 1. Присоединение к лобби через глубокую ссылку
    if context.args and context.args[0].startswith('joinlobby_'):
        lobby_id = context.args[0][10:]  # Убираем 'joinlobby_'
        logger.info(f"🔗 Присоединение к лобби через deep link: {lobby_id}")

        await join_lobby_from_deeplink(update, lobby_id, bot)
        return

    # 2. Присоединение к игре 1 на 1 через глубокую ссылку
    if context.args and context.args[0].startswith('join_'):
        game_code = context.args[0][5:]  # Убираем 'join_'
        logger.info(f"🔗 Присоединение к игре через deep link: {game_code}")

        # TODO: Реализовать присоединение к игре 1 на 1
        await update.message.reply_text(
            f"🎮 Присоединение к игре {game_code}\n\n"
            "⚠️ Функция в разработке...\n"
            "Пока используйте команду: /join <код>"
        )
        return

    # 3. Старая обработка (для обратной совместимости)
    if context.args and context.args[0].startswith('join'):
        game_code = context.args[0][4:]  # Убираем 'join'
        logger.info(f"🔗 Старый формат deep link: {game_code}")

        await update.message.reply_text(
            f"🎮 Присоединение к игре {game_code}\n\n"
            "⚠️ Используйте новую ссылку\n"
            "Пока используйте команду: /join <код>"
        )
        return

    # ========== ОБЫЧНЫЙ СТАРТ ==========

    # Получаем статистику
    stats = bot.db.get_user_stats(user.id)
    balance = stats[1] if stats else 0

    welcome_text = (
        f"🎲 Привет, {user.first_name}!\n\n"
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

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /menu"""
    user = update.effective_user
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "❌ Меню доступно только в личном чате с ботом."
        )
        return

    # Регистрируем если не зарегистрирован
    bot.db.register_user(user.id, user.username, user.first_name)

    # Получаем баланс
    stats = bot.db.get_user_stats(user.id)
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


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /help"""
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        help_text = (
            "🎯 **Команды для игры в группах:**\n\n"
            "/duel <ставка> - создать дуэль\n"
            "Пример: /duel 10\n\n"
            "/join <код> - присоединиться к игре\n\n"
            "📱 *Для пополнения баланса перейдите в личный чат с ботом*"
        )
    else:
        help_text = (
            "❓ **Помощь по игре**\n\n"
            "🎯 Как играть:\n"
            "1. Нажмите 'Создать игру' в меню\n"
            "2. Выберите сумму ставки\n"
            "3. Другой игрок присоединяется по ID\n"
            "4. Бросайте кости\n"
            "5. Победитель забирает банк\n\n"
            "💸 Команды:\n"
            "/menu - открыть меню\n"
            "/join [ID] - присоединиться к игре\n"
            "/duel [ставка] - создать дуэль (в группах)"
        )

    await update.message.reply_text(help_text, parse_mode='Markdown')


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /deposit"""
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "❌ Пополнение доступно только в личном чате.\n"
            "Перейдите в диалог с ботом."
        )
        return

    await update.message.reply_text(
        "💳 Для пополнения баланса используйте меню:\n\n"
        "1. Нажмите /menu\n"
        "2. Выберите 'Пополнить баланс'\n"
        "3. Выберите сумму"
    )


# Остальные команды пока заглушки
async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /join - заглушка"""
    await update.message.reply_text("Функция /join будет добавлена позже")


async def create_lobby_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /create - заглушка"""
    await update.message.reply_text("Функция /create будет добавлена позже")


async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /duel - заглушка"""
    await update.message.reply_text("Функция /duel будет добавлена позже")


async def join_lobby_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /join_lobby - заглушка"""
    await update.message.reply_text("Функция /join_lobby будет добавлена позже")


async def join_lobby_from_deeplink(update, lobby_id, bot):
    """Присоединение к лобби через глубокую ссылку"""
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    logger.info(f"🎮 Присоединение к лобби {lobby_id} пользователем {username}")

    # Проверяем существует ли лобби
    lobby = bot.lobby_manager.get_lobby(lobby_id)
    if not lobby:
        await update.message.reply_text(
            "❌ Лобби не найдено или игра уже началась.\n\n"
            "Возможные причины:\n"
            "• Лобби было удалено\n"
            "• Игра уже началась\n"
            "• Ссылка устарела"
        )
        return

    # Проверяем не присоединился ли уже
    if any(p.id == user_id for p in lobby.players):
        await update.message.reply_text("❌ Вы уже в этом лобби!")
        return

    # Проверяем есть ли свободные места
    if lobby.is_full():
        await update.message.reply_text("❌ Лобби заполнено!")
        return

    # Проверяем баланс
    user_data = bot.db.get_user(user_id)
    if not user_data or user_data[4] < lobby.bet_amount:
        await update.message.reply_text(
            f"❌ Недостаточно средств!\n"
            f"💰 Нужно: ${lobby.bet_amount:.0f}\n\n"
            f"Пополните баланс через меню."
        )
        return

    # Присоединяемся к лобби
    success, message = bot.lobby_manager.join_lobby(lobby_id, user_id, username)

    if success:
        # Списываем ставку
        bot.db.update_balance(user_id, -lobby.bet_amount)

        # Помечаем игрока как оплатившего
        player = lobby.get_player(user_id)
        if player:
            player.paid = True

        # Сохраняем лобби
        bot.lobby_manager.save_lobby_to_db(lobby)

        # Сообщение успеха
        await update.message.reply_text(
            f"✅ Вы присоединились к лобби #{lobby_id}!\n\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n\n"
            f"📋 Информация о лобби отправлена в чат создателя."
        )

        # Уведомляем создателя
        try:
            await bot.application.bot.send_message(
                chat_id=lobby.creator_id,
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!\n"
                     f"👥 Теперь игроков: {len(lobby.players)}/{lobby.max_players}"
            )
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления создателя: {e}")

        # Обновляем сообщение лобби (если возможно)
        if lobby.message_chat_id and lobby.message_id:
            try:
                text = lobby.get_lobby_text()
                keyboard = get_lobby_keyboard(lobby)  # Нужно импортировать из lobby_handlers

                await bot.application.bot.edit_message_text(
                    chat_id=lobby.message_chat_id,
                    message_id=lobby.message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"❌ Ошибка обновления сообщения лобби: {e}")
    else:
        await update.message.reply_text(f"❌ {message}")