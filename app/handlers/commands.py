# app/handlers/commands.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
import logging
from app.handlers.lobby_handlers import get_lobby_keyboard

logger = logging.getLogger(__name__)


def create_main_menu_keyboard():
    """Создает клавиатуру главного меню (единая для всех функций)"""
    keyboard = [
        [
            InlineKeyboardButton("🎯 Создать игру", callback_data="find_game"),
            InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")
        ],
        [
            InlineKeyboardButton("📊 Моя статистика", callback_data="stats"),
            InlineKeyboardButton("❓ Помощь", callback_data="help")
        ],
        [
            InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
            InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


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

    # АДМИН-КОМАНДЫ
    application.add_handler(CommandHandler("admin",
                                           lambda update, context: admin_command(update, context, bot)))
    application.add_handler(CommandHandler("admin_stats",
                                           lambda update, context: admin_stats_command(update, context, bot)))
    application.add_handler(CommandHandler("admin_user",
                                           lambda update, context: admin_user_command(update, context, bot)))
    application.add_handler(CommandHandler("admin_balance",
                                           lambda update, context: admin_balance_command(update, context, bot)))
    application.add_handler(CommandHandler("admin_payments",
                                           lambda update, context: admin_payments_command(update, context, bot)))
    application.add_handler(CommandHandler("admin_broadcast",
                                           lambda update, context: admin_broadcast_command(update, context, bot)))



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

        # ВЫЗЫВАЕМ join_game_command вместо заглушки
        # Нужно имитировать вызов команды /join
        context.args = [game_code]  # Устанавливаем аргументы для join_game_command
        await join_game_command(update, context, bot)
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
    """Обработчик команды /menu"""
    # Если это callback query (из кнопки)
    if hasattr(update, 'callback_query') and update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
    else:
        # Если это команда из сообщения
        user_id = update.effective_user.id
        query = None

    stats = bot.db.get_user_stats(user_id)
    balance = stats[1] if stats else 0

    menu_text = (
        f"🎲 Главное меню\n\n"
        f"💰 Баланс: ${balance:.0f}\n"
        "Выберите действие:"
    )

    # ТА ЖЕ КЛАВИАТУРА
    keyboard = [
        [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
        [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
         InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(menu_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(menu_text, reply_markup=reply_markup)


async def show_main_menu_from_message(update: Update, bot):
    """Показывает главное меню из сообщения"""
    user_id = update.effective_user.id
    stats = bot.db.get_user_stats(user_id)
    balance = stats[1] if stats else 0

    menu_text = (
        f"🎲 Главное меню\n\n"
        f"💰 Баланс: ${balance:.0f}\n"
        "Выберите действие:"
    )

    await update.message.reply_text(menu_text, reply_markup=create_main_menu_keyboard())


async def show_main_menu_from_callback(query, bot):
    """Показывает главное меню из callback query"""
    user_id = query.from_user.id
    stats = bot.db.get_user_stats(user_id)
    balance = stats[1] if stats else 0

    menu_text = (
        f"🎲 Главное меню\n\n"
        f"💰 Баланс: ${balance:.0f}\n"
        "Выберите действие:"
    )

    # ТА ЖЕ КЛАВИАТУРА
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


async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /deposit <сумма>"""
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "❌ Пополнение доступно только в личном чате.\n"
            "Перейдите в диалог с ботом."
        )
        return

    if not context.args:
        await update.message.reply_text(
            "💳 **Использование:** `/deposit <сумма>`\n\n"
            "Примеры:\n"
            "• `/deposit 15.5` - пополнить на $15.50\n"
            "• `/deposit 100` - пополнить на $100\n\n"
            "Минимум: $1\n"
            "Максимум: $1000",
            parse_mode='Markdown'
        )
        return

    try:
        amount = float(context.args[0])

        if amount < 1:
            await update.message.reply_text("❌ Минимальная сумма: $1")
            return

        if amount > 1000:
            await update.message.reply_text("❌ Максимальная сумма: $1000")
            return

        # Пополняем баланс
        user_id = update.effective_user.id
        bot.db.update_balance(user_id, amount)

        await update.message.reply_text(
            f"✅ Баланс пополнен на ${amount:.2f}\n"
            f"💰 Новый баланс: ${bot.db.get_user(user_id)[4]:.2f}"
        )

    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число\n\nПример: /deposit 15.5")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик /withdraw <сумма>"""
    chat = update.effective_chat

    if chat.type in ["group", "supergroup"]:
        await update.message.reply_text(
            "❌ Вывод доступен только в личном чате.\n"
            "Перейдите в диалог с ботом."
        )
        return

    if not context.args:
        user_id = update.effective_user.id
        user = bot.db.get_user(user_id)

        if user:
            balance = user[4]
            await update.message.reply_text(
                f"💸 **Использование:** `/withdraw <сумма>`\n\n"
                f"💰 Доступно: ${balance:.2f}\n\n"
                "Примеры:\n"
                "• `/withdraw 25.75` - вывести $25.75\n"
                "• `/withdraw 50` - вывести $50\n\n"
                "Минимум: $1",
                parse_mode='Markdown'
            )
        return

    try:
        amount = float(context.args[0])

        if amount < 1:
            await update.message.reply_text("❌ Минимальная сумма: $1")
            return

        user_id = update.effective_user.id
        user = bot.db.get_user(user_id)

        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return

        current_balance = user[4]

        if current_balance < amount:
            await update.message.reply_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${current_balance:.2f}\n"
                f"Требуется: ${amount:.2f}"
            )
            return

        # Списываем средства
        bot.db.update_balance(user_id, -amount)

        # Создаем запись о выводе
        try:
            cursor = bot.db.get_connection().cursor()
            cursor.execute("""
                INSERT INTO payments (user_id, amount, payment_type, status, description)
                VALUES (?, ?, 'withdraw', 'pending', ?)
            """, (user_id, amount, f"Запрос на вывод ${amount:.2f}"))
            bot.db.get_connection().commit()

            payment_id = cursor.lastrowid

        except Exception as e:
            logger.error(f"Ошибка создания записи о выводе: {e}")
            bot.db.update_balance(user_id, amount)  # Возвращаем средства
            await update.message.reply_text("❌ Ошибка создания заявки")
            return

        commission = amount * 0.08
        receive_amount = amount - commission

        await update.message.reply_text(
            f"✅ **Запрос на вывод создан!**\n\n"
            f"📝 ID заявки: `{payment_id}`\n"
            f"💵 Запрошено: ${amount:.2f}\n"
            f"📊 Комиссия (8%): ${commission:.2f}\n"
            f"💰 К получению: ${receive_amount:.2f}\n\n"
            f"⏳ Обычно обработка занимает 1-24 часа.\n"
            f"👨‍💼 Для ускорения обратитесь к @admin",
            parse_mode='Markdown'
        )

    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число\n\nПример: /withdraw 25.5")


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

        # Даже если уже в лобби, отправляем персональное сообщение
        await send_personal_lobby_message_to_user(user_id, lobby, bot)
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

        # 1. Успешное сообщение в чате
        await update.message.reply_text(
            f"✅ Вы присоединились к лобби #{lobby_id}!\n\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n\n"
            f"📨 **Вам отправлено персональное сообщение с управлением лобби!**\n"
            f"Проверьте чат с ботом."
        )

        # 2. ОТПРАВЛЯЕМ ПЕРСОНАЛЬНОЕ СООБЩЕНИЕ С КНОПКАМИ
        await send_personal_lobby_message_to_user(user_id, lobby, bot)

        # 3. Уведомляем создателя
        try:
            await bot.application.bot.send_message(
                chat_id=lobby.creator_id,
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!\n"
                     f"👥 Теперь игроков: {len(lobby.players)}/{lobby.max_players}"
            )

            # Также отправляем создателю обновленное сообщение лобби
            await send_personal_lobby_message_to_user(lobby.creator_id, lobby, bot)
        except Exception as e:
            logger.error(f"❌ Ошибка уведомления создателя: {e}")

        # 4. Обновляем сообщение лобби (если возможно)
        if hasattr(lobby, 'message_chat_id') and hasattr(lobby, 'message_id'):
            try:
                from app.handlers.lobby_handlers import get_lobby_keyboard
                text = lobby.get_lobby_text()
                keyboard = get_lobby_keyboard(lobby)

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


async def send_personal_lobby_message_to_user(user_id, lobby, bot):
    """Отправляет персональное сообщение с управлением лобби пользователю"""
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        # Получаем информацию об игроке
        player = lobby.get_player(user_id)
        if not player:
            return

        # Создаем текст сообщения
        ready_count = sum(1 for p in lobby.players if p.ready)
        player_status = "✅ Готов" if player.ready else "❌ Не готов"

        message_text = (
            f"🎮 **Ваше лобби** #{lobby.id}\n\n"
            f"👤 Создатель: {lobby.creator_name}\n"
            f"💰 Ставка: ${lobby.bet_amount:.0f}\n"
            f"👥 Игроков: {len(lobby.players)}/{lobby.max_players}\n"
            f"✅ Готовы: {ready_count}/{len(lobby.players)}\n"
            f"📊 Ваш статус: {player_status}\n\n"
        )

        # Создаем кнопки
        buttons = []

        # Кнопка готовности
        ready_button_text = "✅ Отметить готовность" if not player.ready else "⏸ Снять готовность"
        buttons.append([
            InlineKeyboardButton(
                ready_button_text,
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
        if user_id == lobby.creator_id:
            if lobby.all_players_ready():
                buttons.append([
                    InlineKeyboardButton(
                        "🚀 НАЧАТЬ ИГРУ",
                        callback_data=f"lobby_start:{lobby.id}"
                    )
                ])
            else:
                message_text += f"⏳ Ожидание игроков: {ready_count}/{lobby.max_players} готовы\n"

        keyboard = InlineKeyboardMarkup(buttons)

        # Отправляем сообщение
        await bot.application.bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        logger.info(f"✅ Персональное сообщение лобби отправлено игроку {user_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка отправки персонального сообщения лобби: {e}")


async def join_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработка присоединения через deep link"""
    try:
        if not context.args:
            return

        game_code = context.args[0]
        user_id = update.effective_user.id
        user_name = update.effective_user.username or update.effective_user.first_name

        # Присоединяемся к игре
        game, error = bot.game_manager.join_game(game_code, user_id, user_name)

        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        # Успех
        keyboard = [[InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Вы присоединились к игре {game.game_code}!\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n"
            f"🎲 Готовы бросить кости?",
            reply_markup=reply_markup
        )

        # Уведомляем создателя
        try:
            await context.bot.send_message(
                chat_id=game.player1_id,
                text=f"✅ Игрок {user_name} присоединился к вашей игре {game.game_code}!",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления создателя: {e}")


    except Exception as e:
        logger.error(f"Ошибка присоединения через deep link: {e}")
        await update.message.reply_text("❌ Ошибка присоединения к игре")


# ============ АДМИН-КОМАНДЫ ============

# Список админов (добавьте свои ID)
ADMIN_IDS = [942523120, 5558886328]  # Ваш ID


async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверка прав администратора"""
    user_id = update.effective_user.id
    if user_id in ADMIN_IDS:
        return True

    await update.message.reply_text("❌ Доступ запрещен. Только для администраторов.")
    return False


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Главная админ-панель: /admin"""
    if not await check_admin(update, context):
        return

    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("👤 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🛠️ **Панель администратора**\n\n"
        "Выберите раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Статистика бота: /admin_stats"""
    if not await check_admin(update, context):
        return

    try:
        # Получаем статистику из БД
        cursor = bot.db.get_connection().cursor()

        # Пользователи
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        # Активные пользователи за 24 часа
        cursor.execute("""
            SELECT COUNT(*) FROM users 
            WHERE last_active > datetime('now', '-1 day')
        """)
        active_users = cursor.fetchone()[0]

        # Игры
        cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'finished'")
        finished_games = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(bet_amount * 2) FROM games WHERE status = 'finished'")
        total_bet = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'active'")
        active_games = cursor.fetchone()[0]

        # Платежи
        cursor.execute("""
            SELECT 
                SUM(CASE WHEN payment_type = 'deposit' AND status = 'completed' THEN amount ELSE 0 END),
                SUM(CASE WHEN payment_type = 'withdraw' AND status = 'completed' THEN amount ELSE 0 END)
            FROM payments
        """)
        payments = cursor.fetchone()
        total_deposits = payments[0] or 0
        total_withdrawals = payments[1] or 0

        # Балансы
        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

        stats_text = (
            f"📊 **Статистика бота**\n\n"
            f"👥 Пользователи:\n"
            f"• Всего: {total_users}\n"
            f"• Активные (24ч): {active_users}\n\n"
            f"🎮 Игры:\n"
            f"• Завершено: {finished_games}\n"
            f"• Активные: {active_games}\n"
            f"• Общий оборот: ${total_bet:.2f}\n\n"
            f"💰 Финансы:\n"
            f"• Депозиты: ${total_deposits:.2f}\n"
            f"• Выводы: ${total_withdrawals:.2f}\n"
            f"• Балансы пользователей: ${total_balance:.2f}\n"
            f"• Комиссия бота: ${total_deposits - total_withdrawals:.2f}"
        )

        await update.message.reply_text(stats_text, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def admin_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Информация о пользователе: /admin_user <user_id>"""
    if not await check_admin(update, context):
        return

    try:
        if not context.args:
            await update.message.reply_text("Использование: /admin_user <user_id>")
            return

        user_id = int(context.args[0])

        # Получаем информацию о пользователе
        user = bot.db.get_user(user_id)
        if not user:
            await update.message.reply_text(f"❌ Пользователь {user_id} не найден")
            return

        # Получаем статистику игр
        cursor = bot.db.get_connection().cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_games,
                SUM(CASE WHEN (p1_tg_id = ? AND winner_id = ?) OR (p2_tg_id = ? AND winner_id = ?) THEN 1 ELSE 0 END) as wins
            FROM games 
            WHERE status = 'finished'
        """, (user_id, user_id, user_id, user_id))

        games_stats = cursor.fetchone()
        total_games = games_stats[0] or 0
        wins = games_stats[1] or 0

        user_info = (
            f"👤 **Информация о пользователе**\n\n"
            f"🆔 ID: {user[0]}\n"
            f"📛 Имя: {user[2]}\n"
            f"👤 Username: @{user[1] or 'нет'}\n"
            f"💰 Баланс: ${user[4]:.2f}\n"
            f"🕐 Регистрация: {user[5]}\n"
            f"🔄 Последняя активность: {user[6] or 'никогда'}\n\n"
            f"🎮 **Статистика игр:**\n"
            f"• Всего игр: {total_games}\n"
            f"• Побед: {wins}\n"
            f"• Поражений: {total_games - wins}\n"
            f"• Winrate: {wins / max(total_games, 1) * 100:.1f}%"
        )

        await update.message.reply_text(user_info, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка admin_user: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def admin_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Изменение баланса: /admin_balance <user_id> <сумма>"""
    if not await check_admin(update, context):
        return

    try:
        if len(context.args) < 2:
            await update.message.reply_text(
                "Использование: /admin_balance <user_id> <сумма>\n"
                "Пример: /admin_balance 123456789 100"
            )
            return

        user_id = int(context.args[0])
        amount = float(context.args[1])

        # Обновляем баланс
        bot.db.update_balance(user_id, amount)

        # Получаем новый баланс
        user = bot.db.get_user(user_id)
        new_balance = user[4] if user else amount

        await update.message.reply_text(
            f"✅ Баланс пользователя {user_id} изменен\n"
            f"💰 Добавлено: ${amount:.2f}\n"
            f"💳 Новый баланс: ${new_balance:.2f}"
        )

    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа")
    except Exception as e:
        logger.error(f"Ошибка admin_balance: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def admin_payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Просмотр платежей: /admin_payments [статус]"""
    if not await check_admin(update, context):
        return

    try:
        status_filter = context.args[0] if context.args else None

        cursor = bot.db.get_connection().cursor()

        if status_filter:
            cursor.execute("""
                SELECT payment_id, user_id, amount, payment_type, status, created_at 
                FROM payments 
                WHERE status = ? 
                ORDER BY created_at DESC 
                LIMIT 20
            """, (status_filter,))
        else:
            cursor.execute("""
                SELECT payment_id, user_id, amount, payment_type, status, created_at 
                FROM payments 
                ORDER BY created_at DESC 
                LIMIT 20
            """)

        payments = cursor.fetchall()

        if not payments:
            await update.message.reply_text("📭 Платежей не найдено")
            return

        payment_list = "💰 **Последние платежи:**\n\n"
        for payment in payments:
            payment_id, user_id, amount, p_type, status, created_at = payment
            payment_list += (
                f"🆔 {payment_id}\n"
                f"👤 {user_id} | {p_type} | ${amount:.2f}\n"
                f"📊 {status} | {created_at}\n"
                f"────────────────────\n"
            )

        await update.message.reply_text(payment_list[:4000], parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка admin_payments: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Рассылка сообщения всем пользователям: /admin_broadcast <текст>"""
    if not await check_admin(update, context):
        return

    try:
        if not context.args:
            await update.message.reply_text(
                "Использование: /admin_broadcast <текст сообщения>\n\n"
                "Пример: /admin_broadcast Новое обновление! Добавлены новые игры."
            )
            return

        message_text = " ".join(context.args)

        # Подтверждение
        keyboard = [
            [InlineKeyboardButton("✅ Да, отправить", callback_data=f"broadcast_confirm_{hash(message_text)}")],
            [InlineKeyboardButton("❌ Нет, отменить", callback_data="broadcast_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"📢 **Предпросмотр рассылки:**\n\n"
            f"{message_text}\n\n"
            f"----------------\n"
            f"ℹ️ Отправить это сообщение всем пользователям?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Сохраняем текст в контексте
        context.user_data['broadcast_text'] = message_text

    except Exception as e:
        logger.error(f"Ошибка admin_broadcast: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")