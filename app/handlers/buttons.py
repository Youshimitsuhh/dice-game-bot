# app/handlers/buttons.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
import logging

logger = logging.getLogger(__name__)

ADMIN_IDS = [942523120, 5558886328]


def register_button_handlers(application, bot):
    """Регистрируем обработчики inline-кнопок"""
    logger.info("🔘 Регистрируем обработчики кнопок")

    # Общий обработчик для большинства кнопок
    application.add_handler(CallbackQueryHandler(
        lambda update, context: button_handler(update, context, bot)
    ))

    # Обработчик админ-кнопок (дополнительный, для приоритета)
    application.add_handler(CallbackQueryHandler(
        lambda update, context: handle_admin_callback(update, context, bot),
        pattern=r"^(admin_|broadcast_)"
    ), group=0)  # group=0 для более высокого приоритета


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Основной обработчик inline-кнопок"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"🔘 Нажата кнопка: '{data}' пользователем {user_id}")

    # ========== ВАЖНО: Пропускаем кнопки ЛОББИ ==========
    lobby_prefixes = ("lobby_bet_", "lobby_size_", "lobby_custom_bet",
                      "lobby_cancel", "lobby_toggle_ready:",
                      "lobby_start:", "lobby_leave:", "join_lobby:")

    if any(data.startswith(prefix) for prefix in lobby_prefixes):
        logger.info(f"🔘 Кнопка лобби '{data}' передана в lobby_handlers")
        return

    # ========== ВАЖНО: Пропускаем кнопки ДУЭЛЕЙ ==========
    duel_prefixes = ("duel_accept_", "duel_roll_", "duel_cancel_")

    if any(data.startswith(prefix) for prefix in duel_prefixes):
        logger.info(f"🔘 Кнопка дуэли '{data}' передана в duel_handlers")
        return

    # ========== ВАЖНО: Пропускаем кнопки ПЛАТЕЖЕЙ ==========
    payment_prefixes = ("deposit", "withdraw", "check_deposit",
                        "cancel_withdraw", "payment_history", "payment_cancel")

    admin_prefixes = ("admin_", "broadcast_")

    if any(data.startswith(prefix) for prefix in admin_prefixes):
        logger.info(f"🔘 Кнопка админ-панели '{data}' передана в админ-обработчик")
        await handle_admin_callback(update, context, bot)
        return

    if any(data.startswith(prefix) for prefix in payment_prefixes):
        logger.info(f"🔘 Кнопка платежа '{data}' передана в payment_handlers")
        return

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

        # АВТОМАТИЧЕСКОЕ ВОЗВРАЩЕНИЕ В ГЛАВНОЕ МЕНЮ

        try:

            # Получаем статистику пользователя

            user_data = bot.db.get_user(user_id)

            if user_data:

                balance = user_data[4]  # balance на 5-й позиции

                username = user_data[1] or user_data[3] or "Игрок"

            else:

                balance = 0.0

                username = "Игрок"

            # Создаем текст меню

            menu_text = (

                f"🎲 Главное меню\n\n"

                f"👤 {username}\n"

                f"💰 Баланс: ${balance:.2f}\n\n"

                "Выберите действие:"

            )

            # Создаем клавиатуру

            keyboard = [

                [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],

                [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],

                [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],

                [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),

                 InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],

                [InlineKeyboardButton("❓ Помощь", callback_data="help")]

            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            # Обновляем сообщение

            await query.edit_message_text(

                text=menu_text,

                reply_markup=reply_markup,

                parse_mode='Markdown'

            )

            logger.info(f"✅ Пользователь {user_id} вернулся в главное меню")


        except Exception as e:

            logger.error(f"❌ Ошибка возврата в меню: {e}")

            # Резервное меню при ошибке

            await query.edit_message_text(

                "📋 **Главное меню**\n\n"

                "Что-то пошло не так, но вы в меню!\n\n"

                "Используйте команды:\n"

                "/menu - обновить меню\n"

                "/deposit - пополнить баланс\n"

                "/withdraw - вывести средства\n"

                "/balance - баланс и статистика",

                reply_markup=InlineKeyboardMarkup([

                    [InlineKeyboardButton("🔄 Обновить меню", callback_data="main_menu")]

                ])

            )

        return

    elif data == "help":
        await show_help(query, bot)

    # elif data == "deposit":
    #     await show_deposit(query, bot)
    #
    # elif data == "withdraw":
    #     await show_withdraw(query, bot)

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

    # # Платежи
    # elif data.startswith("deposit_"):
    #     amount = float(data.split("_")[1])
    #     await process_deposit(query, amount, bot)
    #
    # elif data == "custom_deposit":
    #     context.user_data['waiting_for_deposit'] = True
    #     await ask_custom_deposit(query, bot)
    #
    # elif data.startswith("withdraw_"):
    #     amount = float(data.split("_")[1])
    #     await process_withdraw(query, amount, bot)
    #
    # elif data == "custom_withdraw":
    #     context.user_data['waiting_for_withdraw'] = True
    #     await ask_custom_withdraw(query, bot)

    # Дуэли (должны были быть обработаны выше)
    elif data.startswith("duel_"):
        # Если мы здесь - значит это неизвестный тип дуэли
        logger.warning(f"⚠️ Неизвестная кнопка дуэли: {data}")
        # Можно либо игнорировать, либо показать сообщение
        # await query.edit_message_text("⚔️ Эта функция дуэли еще не реализована")

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


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, bot):
    """Обработчик callback кнопок админ-панели"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    try:
        # Проверяем админские права (нужно импортировать ADMIN_IDS из commands.py или config)
        # Временно используем список админов здесь

        if user_id not in ADMIN_IDS:
            await query.edit_message_text("❌ Доступ запрещен. Только для администраторов.")
            return

        logger.info(f"🔘 Админ-кнопка: '{data}' пользователем {user_id}")

        if data == "admin_stats":
            await show_admin_stats(query, bot)

        elif data == "admin_payments":
            await show_admin_payments_menu(query)

        elif data == "admin_users":
            await show_admin_users_menu(query)

        elif data == "admin_user_search":  # ← ДОБАВЬТЕ ЭТО
            await query.edit_message_text(
                "🔍 **Поиск пользователя**\n\n"
                "Введите ID пользователя или username:\n\n"
                "Примеры:\n"
                "• `123456789`\n"
                "• `@username`\n\n"
                "Или используйте команду:\n"
                "`/admin_user <ID>`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="admin_users")]
                ])
            )

        elif data == "admin_games":
            await show_admin_games_menu(query)

        elif data == "admin_games_active":
            await show_admin_games_active(query, bot)

        elif data == "admin_games_history":
            await show_admin_games_history(query, bot)

        elif data == "admin_broadcast":
            await query.edit_message_text(
                "📢 **Рассылка сообщений**\n\n"
                "Для рассылки используйте команду:\n"
                "`/admin_broadcast <текст сообщения>`\n\n"
                "Пример: /admin_broadcast Привет всем! Добавлены новые игры.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
                ])
            )

        elif data == "admin_settings":
            await show_admin_settings(query, bot)

        elif data == "admin_back":
            await show_admin_main_menu(query)

        elif data.startswith("broadcast_"):
            if data == "broadcast_cancel":
                await show_admin_main_menu(query)
            elif data.startswith("broadcast_confirm_"):
                await process_broadcast_confirmation(query, context, bot)

        elif data == "admin_payments_all":
            await show_admin_payments_list(query, bot)

        elif data == "admin_payments_pending":
            await show_admin_pending_withdrawals(query, bot)

        else:
            await query.edit_message_text(f"❌ Неизвестная админ-команда: {data}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки админ-колбэка: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


async def show_admin_main_menu(query):
    """Показывает главное меню админ-панели"""
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Платежи", callback_data="admin_payments")],
        [InlineKeyboardButton("👤 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("🎮 Управление играми", callback_data="admin_games")],
        [InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🛠️ **Панель администратора**\n\n"
        "Выберите раздел:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_admin_stats(query, bot):
    """Показывает статистику бота"""
    try:
        cursor = bot.db.get_connection().cursor()

        # Пользователи (простой подсчет)
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0] or 0

        # Игры
        cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'finished'")
        finished_games = cursor.fetchone()[0] or 0

        cursor.execute("SELECT SUM(bet_amount * 2) FROM games WHERE status = 'finished'")
        total_bet_result = cursor.fetchone()
        total_bet = float(total_bet_result[0]) if total_bet_result and total_bet_result[0] else 0.0

        # Активные игры
        cursor.execute("SELECT COUNT(*) FROM games WHERE status = 'active'")
        active_games = cursor.fetchone()[0] or 0

        # Платежи
        cursor.execute("""
            SELECT 
                COALESCE(SUM(CASE WHEN payment_type = 'deposit' AND status = 'completed' THEN amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN payment_type = 'withdraw' AND status = 'completed' THEN amount ELSE 0 END), 0)
            FROM payments
        """)
        payments = cursor.fetchone()
        total_deposits = float(payments[0]) if payments and payments[0] else 0.0
        total_withdrawals = float(payments[1]) if payments and payments[1] else 0.0

        # Балансы пользователей
        cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM users")
        total_balance_result = cursor.fetchone()
        total_balance = float(total_balance_result[0]) if total_balance_result and total_balance_result[0] else 0.0

        stats_text = (
            f"📊 **Статистика бота**\n\n"
            f"👥 **Пользователи:** {total_users}\n"
            f"🎮 **Игры:**\n"
            f"• Завершено: {finished_games}\n"
            f"• Активные: {active_games}\n"
            f"• Общий оборот: ${total_bet:.2f}\n\n"
            f"💰 **Финансы:**\n"
            f"• Депозиты: ${total_deposits:.2f}\n"
            f"• Выводы: ${total_withdrawals:.2f}\n"
            f"• Балансы пользователей: ${total_balance:.2f}\n"
            f"• Комиссия бота: ${total_deposits - total_withdrawals:.2f}"
        )

        keyboard = [[InlineKeyboardButton("🔄 Обновить", callback_data="admin_stats"),
                     InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка показа статистики: {e}")
        # Простая версия при ошибке
        await query.edit_message_text(
            f"📊 **Статистика бота**\n\n"
            f"⚠️ Ошибка получения полной статистики.\n"
            f"ℹ️ Используйте команды:\n"
            f"• `/admin_stats` - попробовать снова\n"
            f"• `/admin_payments` - просмотр платежей\n"
            f"• `/admin_user <ID>` - информация о пользователе\n\n"
            f"❌ Ошибка: {str(e)[:100]}",
            await query.edit_message_text(stats_text, reply_markup=reply_markup, parse_mode='Markdown'),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
            ])
        )


async def show_admin_payments_menu(query):
    """Меню управления платежами"""
    keyboard = [
        [InlineKeyboardButton("📋 Все платежи", callback_data="admin_payments_all")],
        [InlineKeyboardButton("⏳ Ожидающие выводы", callback_data="admin_payments_pending")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "💰 **Управление платежами**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_admin_payments_list(query, bot):
    """Показывает список всех платежей"""
    try:
        cursor = bot.db.get_connection().cursor()
        cursor.execute("""
            SELECT payment_id, user_id, amount, payment_type, status, created_at 
            FROM payments 
            ORDER BY created_at DESC 
            LIMIT 15
        """)

        payments = cursor.fetchall()

        if not payments:
            payment_list = "📭 Платежей не найдено"
        else:
            payment_list = "💰 Последние платежи:\n\n"
            for payment in payments:
                payment_id, user_id, amount, p_type, status, created_at = payment
                payment_list += f"{payment_id} | 👤{user_id} | {p_type} | ${amount:.2f} | {status}\n"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_payments")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # ИСПРАВЛЕНО: используем payment_list вместо text
        await query.edit_message_text(payment_list, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка показа платежей: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")

    except Exception as e:
        logger.error(f"Ошибка показа платежей: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


async def show_admin_pending_withdrawals(query, bot):
    """Показывает ожидающие выводы"""
    try:
        cursor = bot.db.get_connection().cursor()
        cursor.execute("""
            SELECT payment_id, user_id, amount, created_at 
            FROM payments 
            WHERE payment_type = 'withdraw' AND status = 'pending'
            ORDER BY created_at DESC
        """)

        withdrawals = cursor.fetchall()

        if not withdrawals:
            withdrawals_text = "✅ Нет ожидающих выводов"
        else:
            withdrawals_text = "⏳ **Ожидающие выводы:**\n\n"
            total_pending = 0
            for w in withdrawals:
                payment_id, user_id, amount, created_at = w
                withdrawals_text += f"• {payment_id}: ${amount:.2f} (👤{user_id})\n"
                total_pending += amount

            withdrawals_text += f"\n💰 Всего на вывод: ${total_pending:.2f}"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_payments")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(withdrawals_text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка показа выводов: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


async def show_admin_games_active(query, bot):
    """Показывает активные игры"""
    try:
        cursor = bot.db.get_connection().cursor()
        # Узнайте структуру таблицы games
        cursor.execute("PRAGMA table_info(games)")
        columns = cursor.fetchall()
        print(f"Структура таблицы games: {columns}")  # Для отладки

        # Временный простой запрос
        cursor.execute("""
            SELECT id, game_code, bet_amount, status, created_at
            FROM games 
            WHERE status = 'active'
            ORDER BY created_at DESC
            LIMIT 10
        """)

        games = cursor.fetchall()

        if not games:
            games_text = "🎮 Активные игры\n\nНет активных игр"
        else:
            games_text = "🎮 Активные игры:\n\n"
            for game in games:
                game_id, game_code, bet_amount, status, created_at = game
                games_text += f"🆔 {game_code}\n💰 ${bet_amount:.2f} | Статус: {status}\n"

        await query.edit_message_text(
            games_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_games_active"),
                 InlineKeyboardButton("🔙 Назад", callback_data="admin_games")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка показа активных игр: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


async def show_admin_games_history(query, bot):
    """Показывает историю игр"""
    try:
        cursor = bot.db.get_connection().cursor()
        # Временный простой запрос
        cursor.execute("""
            SELECT id, game_code, bet_amount, status, created_at
            FROM games 
            WHERE status = 'finished'
            ORDER BY created_at DESC
            LIMIT 10
        """)

        games = cursor.fetchall()

        if not games:
            games_text = "📋 История игр\n\nНет завершенных игр"
        else:
            games_text = "📋 Последние игры:\n\n"
            for game in games:
                game_id, game_code, bet_amount, status, created_at = game
                games_text += f"🆔 {game_code}\n💰 ${bet_amount:.2f}\n"

        await query.edit_message_text(
            games_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить", callback_data="admin_games_history"),
                 InlineKeyboardButton("🔙 Назад", callback_data="admin_games")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка показа истории игр: {e}")
        await query.edit_message_text(f"❌ Ошибка: {str(e)}")


async def show_admin_users_menu(query):
    """Меню управления пользователями"""
    keyboard = [
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "👤Управление пользователями\n\n"
        "Используйте команды:\n"
        "• `/admin_user <ID>` - информация о пользователе\n"
        "• `/admin_balance <ID> <сумма>` - изменить баланс\n\n"
        "Пример: `/admin_user 123456789`",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def show_admin_games_menu(query):
    """Меню управления играми"""
    keyboard = [
        [InlineKeyboardButton("🎮 Активные игры", callback_data="admin_games_active")],
        [InlineKeyboardButton("📋 История игр", callback_data="admin_games_history")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🎮 Управление играми\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_admin_settings(query, bot):
    """Настройки админ-панели"""
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить данные", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⚙️Настройки\n\n"
        "Используйте команды для управления ботом.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def process_broadcast_confirmation(query, context, bot):
    """Обработка подтверждения рассылки"""
    try:
        broadcast_text = context.user_data.get('broadcast_text')
        if not broadcast_text:
            await query.edit_message_text("❌ Текст рассылки не найден")
            return

        await query.edit_message_text("📢 Рассылка начата...")

        # Получаем всех пользователей
        cursor = bot.db.get_connection().cursor()
        cursor.execute("SELECT telegram_id FROM users")
        users = cursor.fetchall()

        success_count = 0
        fail_count = 0

        for user in users:
            try:
                await bot.application.bot.send_message(
                    chat_id=user[0],
                    text=broadcast_text
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки пользователю {user[0]}: {e}")
                fail_count += 1

        await query.edit_message_text(
            f"✅ Рассылка завершена!\n\n"
            f"📊 Статистика:\n"
            f"• Успешно: {success_count}\n"
            f"• Не удалось: {fail_count}\n"
            f"• Всего: {success_count + fail_count}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 В админ-панель", callback_data="admin_back")]
            ])
        )

    except Exception as e:
        logger.error(f"❌ Ошибка рассылки: {e}")
        await query.edit_message_text(f"❌ Ошибка рассылки: {str(e)}")


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
        "👥Создание мультиплеерного лобби\n\n"
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


# async def show_deposit(query, bot):
#     """Показывает варианты депозита"""
#     keyboard = [
#         [InlineKeyboardButton("$10", callback_data="deposit_10")],
#         [InlineKeyboardButton("$25", callback_data="deposit_25")],
#         [InlineKeyboardButton("$50", callback_data="deposit_50")],
#         [InlineKeyboardButton("$100", callback_data="deposit_100")],
#         [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],
#         [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
#     ]
#     reply_markup = InlineKeyboardMarkup(keyboard)
#
#     await query.edit_message_text("💳 Выберите сумму для пополнения:", reply_markup=reply_markup)
#
#
# async def show_withdraw(query, bot):
#     """Показывает варианты вывода"""
#     user_id = query.from_user.id
#     user = bot.db.get_user(user_id)
#
#     if user:
#         balance = user[4]
#         keyboard = [
#             [InlineKeyboardButton("$10", callback_data="withdraw_10")],
#             [InlineKeyboardButton("$25", callback_data="withdraw_25")],
#             [InlineKeyboardButton("$50", callback_data="withdraw_50")],
#             [InlineKeyboardButton("$100", callback_data="withdraw_100")],
#             [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_withdraw")],
#             [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
#         ]
#         reply_markup = InlineKeyboardMarkup(keyboard)
#
#         await query.edit_message_text(
#             f"💸 Вывод средств\n\n"
#             f"💰 Доступно: ${balance:.0f}\n"
#             "Выберите сумму для вывода:",
#             reply_markup=reply_markup
#         )
#
#
# async def process_deposit(query, amount, bot):
#     """Обрабатывает депозит - заглушка"""
#     await query.edit_message_text(
#         f"💳 Депозит на ${amount:.0f}\n\n"
#         "⚠️ Функция в разработке...\n"
#         "Скоро будет доступно!",
#         reply_markup=InlineKeyboardMarkup([
#             [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
#         ])
#     )
#
#
# async def ask_custom_deposit(query, bot):
#     """Запрашивает произвольную сумму депозита"""
#     await query.edit_message_text(
#         "💵 Введите сумму для пополнения (минимум $1):\n\n"
#         "Пример: 15.5 или 75",
#         reply_markup=InlineKeyboardMarkup([
#             [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
#         ])
#     )


async def cancel_active_game(query, game_id, bot):
    """Отменяет активную игру"""
    try:
        user_id = query.from_user.id

        # Вызываем async метод cancel_game с context
        success, message = await bot.game_manager.cancel_game(
            game_id=game_id,
            user_id=user_id,
            context=query
        )

        if success:
            await query.edit_message_text(
                "✅ Игра успешно отменена. Средства возвращены на баланс.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                f"❌ {message}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ])
            )

    except Exception as e:
        logger.error(f"Ошибка отмены игры: {e}")
        await query.edit_message_text(
            "❌ Произошла ошибка при отмене игры.",
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


