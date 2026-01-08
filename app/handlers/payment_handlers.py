from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters
import logging
import re

logger = logging.getLogger(__name__)


# ==================== КОМАНДЫ ====================

async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /deposit - сразу запрашивает сумму"""
    user = update.effective_user

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'payment_manager'):
            await update.message.reply_text("❌ Платежная система не инициализирована")
            return

        balance = bot.payment_manager.get_user_balance(user.id)

        # Если есть аргумент - сразу создаем депозит
        if context.args:
            try:
                amount = float(context.args[0])
                if amount < 1.0:
                    await update.message.reply_text("❌ Минимальная сумма депозита: $1")
                    return
                if amount > 10000.0:
                    await update.message.reply_text("❌ Максимальная сумма депозита: $10,000")
                    return

                # Создаем депозит
                payment, pay_url, error = await bot.payment_manager.create_deposit(
                    user_id=user.id,
                    amount_usd=amount,
                    description=f"Депозит от {user.first_name}"
                )

                if error:
                    await update.message.reply_text(f"❌ {error}")
                    return

                # Показываем кнопку для оплаты
                keyboard = [
                    [InlineKeyboardButton("💳 Оплатить в Telegram", url=pay_url)],
                    [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_deposit_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"💰 Чек на оплату создан!\n\n"
                    f"📝 ID платежа: `{payment.payment_id}`\n"
                    f"💵 Сумма: ${amount:.2f}\n"
                    f"⏳ Срок действия: 24 часа\n\n"
                    f"Нажмите кнопку для оплаты в Telegram:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return

            except ValueError:
                pass  # Не число, показываем запрос суммы

        # Запрашиваем сумму
        context.user_data['waiting_for_deposit'] = True

        await update.message.reply_text(
            f"💳 Пополнение баланса\n\n"
            f"💰 Текущий баланс: ${balance:.2f}\n\n"
            "Введите сумму в USD (например: 15.5 или 75):\n\n"
            "💸 Минимальная сумма: $1\n"
            "🏦 Максимальная сумма: $10,000",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Отмена", callback_data="payment_cancel")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка в deposit_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании депозита")


async def withdraw_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /withdraw - сразу запрашивает сумму"""
    user = update.effective_user

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'payment_manager'):
            await update.message.reply_text("❌ Платежная система не инициализирована")
            return

        balance = bot.payment_manager.get_user_balance(user.id)

        if balance < 5.0:
            await update.message.reply_text(
                f"❌ Недостаточно средств для вывода\n"
                f"💰 Ваш баланс: ${balance:.2f}\n"
                f"💸 Минимальная сумма вывода: $5\n\n"
                f"Используйте /deposit для пополнения баланса"
            )
            return

        # Если есть аргумент - сразу создаем вывод
        if context.args:
            try:
                amount = float(context.args[0])

                if amount < 5.0:
                    await update.message.reply_text("❌ Минимальная сумма вывода: $5")
                    return
                if amount > 5000.0:
                    await update.message.reply_text("❌ Максимальная сумма вывода: $5,000")
                    return
                if amount > balance:
                    await update.message.reply_text(f"❌ Недостаточно средств. Доступно: ${balance:.2f}")
                    return

                # Создаем запрос на вывод
                payment, error = await bot.payment_manager.create_withdrawal(
                    user_id=user.id,
                    amount_usd=amount,
                    description=f"Вывод средств от {user.first_name}"
                )

                if error:
                    await update.message.reply_text(f"❌ {error}")
                    return

                # Расчет комиссии
                commission = amount * 0.08
                receive_amount = amount - commission

                keyboard = [
                    [InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"✅ Запрос на вывод создан!\n\n"
                    f"📝 ID заявки: `{payment.payment_id}`\n"
                    f"💵 Запрошено: ${amount:.2f}\n"
                    f"📊 Комиссия (8%): ${commission:.2f}\n"
                    f"💰 К получению: ${receive_amount:.2f}\n\n"
                    f"⏳ Обычно обработка занимает 1-24 часа.\n"
                    f"Вы можете отменить заявку в течение 10 минут.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                return

            except ValueError:
                pass  # Не число, показываем запрос суммы

        # Запрашиваем сумму
        context.user_data['waiting_for_withdraw'] = True

        await update.message.reply_text(
            f"💸 Вывод средств\n\n"
            f"💰 Доступно для вывода: ${balance:.2f}\n\n"
            "Введите сумму в USD (например: 25.5 или 100):\n\n"
            "💸 Минимальная сумма: $5\n"
            "🏦 Максимальная сумма: $5,000\n"
            "📊 Комиссия системы: 8%",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Отмена", callback_data="payment_cancel")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка в withdraw_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании запроса на вывод")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /balance"""
    user = update.effective_user

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'payment_manager'):
            await update.message.reply_text("❌ Платежная система не инициализирована")
            return

        balance = bot.payment_manager.get_user_balance(user.id)
        stats = bot.payment_manager.get_payment_stats(user.id)

        stats_text = (
            f"💰 Ваш баланс: ${balance:.2f}**\n\n"
            f"📊 Статистика платежей:**\n"
            f"• Всего пополнено: ${stats['total_deposits']:.2f}\n"
            f"• Всего выведено: ${stats['total_withdrawals']:.2f}\n"
            f"• Ожидает вывода: ${stats['pending_withdrawals']:.2f}\n"
            f"• Всего транзакций: {stats['total_payments']}\n\n"
        )

        # Получаем последние платежи
        recent_payments = bot.payment_manager.get_user_payments(user.id, limit=5)

        if recent_payments:
            stats_text += "📋 Последние операции:\n"
            for payment in recent_payments:
                payment_id, amount, currency, status, ptype, created_at, desc = payment
                emoji = "📥" if ptype == "deposit" else "📤"
                status_emoji = "✅" if status == "completed" else "⏳" if status == "pending" else "❌"
                date = created_at[:10] if len(created_at) > 10 else created_at

                stats_text += f"{emoji} {status_emoji} ${amount:.2f} ({ptype}) - {date}\n"

        keyboard = [
            [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
            [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")],
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            stats_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Ошибка в balance_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении баланса")


# ==================== ОБРАБОТЧИКИ КНОПОК ====================

async def payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик кнопок платежей"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    logger.info(f"💰 Payment callback: '{data}' от пользователя {user_id}")

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'payment_manager'):
            await query.edit_message_text("❌ Платежная система не инициализирована")
            return

        # ========== ОСНОВНЫЕ КНОПКИ ИЗ ГЛАВНОГО МЕНЮ ==========

        # КНОПКА "ПОПОЛНИТЬ БАЛАНС"
        if data == "deposit":
            print(f"🔍 DEBUG: Обработка deposit")
            # Запрашиваем сумму депозита
            context.user_data['waiting_for_deposit'] = True

            balance = bot.payment_manager.get_user_balance(user_id)

            await query.edit_message_text(
                f"💳 Пополнение баланса\n\n"
                f"💰 Текущий баланс: ${balance:.2f}\n\n"
                "Введите сумму в USD (например: 15.5 или 75):\n\n"
                "💸 Минимальная сумма: $1\n"
                "🏦 Максимальная сумма: $10,000",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
                ])
            )
            return

        # КНОПКА "ВЫВЕСТИ СРЕДСТВА"
        elif data == "withdraw":
            print(f"🔍 DEBUG: Обработка withdraw")
            balance = bot.payment_manager.get_user_balance(user_id)

            if balance < 5.0:
                await query.answer(
                    f"❌ Недостаточно средств для вывода\n"
                    f"💰 Ваш баланс: ${balance:.2f}\n"
                    f"💸 Минимальная сумма вывода: $5",
                    show_alert=True
                )
                return

            # Запрашиваем сумму вывода
            context.user_data['waiting_for_withdraw'] = True

            await query.edit_message_text(
                f"💸 Вывод средств\n\n"
                f"💰 Доступно для вывода: ${balance:.2f}\n\n"
                "Введите сумму в USD (например: 25.5 или 100):\n\n"
                "💸 Минимальная сумма: $5\n"
                "🏦 Максимальная сумма: $5,000\n"
                "📊 Комиссия системы: 8%",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]
                ])
            )
            return

        # ========== КНОПКИ С ФИКСИРОВАННЫМИ СУММАМИ (ЕСЛИ ОСТАВЛЯЕМ) ==========

        # КНОПКИ С ФИКСИРОВАННЫМИ СУММАМИ ДЕПОЗИТА
        elif data.startswith("deposit_"):
            try:
                amount = float(data.split("_")[1])

                # Создаем депозит
                payment, pay_url, error = await bot.payment_manager.create_deposit(
                    user_id=user_id,
                    amount_usd=amount,
                    description=f"Депозит от пользователя {user_id}"
                )

                if error:
                    await query.answer(f"❌ {error}", show_alert=True)
                    return

                keyboard = [
                    [InlineKeyboardButton("💳 Оплатить в Telegram", url=pay_url)],
                    [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_deposit_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"💰 Чек на оплату создан!\n\n"
                    f"📝 ID платежа: `{payment.payment_id}`\n"
                    f"💵 Сумма: ${amount:.2f}\n"
                    f"⏳ Срок действия: 24 часа\n\n"
                    f"Нажмите кнопку для оплаты в Telegram:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            except Exception as e:
                logger.error(f"Ошибка создания депозита: {e}")
                await query.answer("❌ Ошибка создания платежа", show_alert=True)
            return

        # КНОПКИ С ФИКСИРОВАННЫМИ СУММАМИ ВЫВОДА
        elif data.startswith("withdraw_"):
            try:
                amount = float(data.split("_")[1])

                # Создаем запрос на вывод
                payment, error = await bot.payment_manager.create_withdrawal(
                    user_id=user_id,
                    amount_usd=amount,
                    description=f"Вывод средств пользователя {user_id}"
                )

                if error:
                    await query.answer(f"❌ {error}", show_alert=True)
                    return

                commission = amount * 0.08
                receive_amount = amount - commission

                keyboard = [
                    [InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(
                    f"✅ Запрос на вывод создан!\n\n"
                    f"📝 ID заявки: `{payment.payment_id}`\n"
                    f"💵 Запрошено: ${amount:.2f}\n"
                    f"📊 Комиссия (8%): ${commission:.2f}\n"
                    f"💰 К получению: ${receive_amount:.2f}\n\n"
                    f"⏳ Обычно обработка занимает 1-24 часа.\n"
                    f"Вы можете отменить заявку в течение 10 минут.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            except Exception as e:
                logger.error(f"Ошибка создания вывода: {e}")
                await query.answer("❌ Ошибка создания вывода", show_alert=True)
            return

        # ========== ОСТАЛЬНЫЕ КНОПКИ ==========

        # ПРОВЕРКА СТАТУСА ДЕПОЗИТА
        elif data.startswith("check_deposit_"):
            payment_id = data.split("_")[2]
            await check_deposit_status(query, payment_id, bot)
            return

        # ОТМЕНА ВЫВОДА
        elif data.startswith("cancel_withdraw_"):
            payment_id = data.split("_")[2]
            await cancel_withdrawal(query, payment_id, bot, user_id)
            return

        # ИСТОРИЯ ПЛАТЕЖЕЙ
        elif data == "payment_history":
            await show_payment_history(query, bot, user_id)
            return


        # ========== ПЕРЕНАПРАВЛЕНИЕ НЕПЛАТЕЖНЫХ КНОПОК ==========

        # КНОПКА "ПРОИЗВОЛЬНАЯ СТАВКА" - должна быть в buttons.py
        elif data == "custom_bet":
            print(f"🔍 DEBUG: custom_bet попала в payment_handlers, перенаправляем...")
            try:
                # Импортируем функцию из buttons.py
                from app.handlers.buttons import ask_custom_bet
                await ask_custom_bet(query, bot)
            except ImportError as e:
                print(f"🔍 DEBUG: Ошибка импорта ask_custom_bet: {e}")
                # Показываем простой запрос
                await query.edit_message_text(
                    "💵 Введите сумму ставки (минимум $1):\n\n"
                    "Пример: 15 или 75.5",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
                    ])
                )
            return

        # КНОПКА "custom_deposit"
        elif data == "custom_deposit":
            print(f"🔍 DEBUG: Обработка custom_deposit")
            context.user_data['waiting_for_deposit'] = True
            await query.edit_message_text(
                "💵 Произвольная сумма депозита\n\n"
                "Введите сумму в USD (например: 15.5 или 75):\n\n"
                "💸 Минимальная сумма: $1\n"
                "🏦 Максимальная сумма: $10,000",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Назад в меню", callback_data="main_menu")]
                ])
            )
            return

        # КНОПКА "custom_withdraw"
        elif data == "custom_withdraw":
            print(f"🔍 DEBUG: Обработка custom_withdraw")
            context.user_data['waiting_for_withdraw'] = True
            balance = bot.payment_manager.get_user_balance(user_id)

            await query.edit_message_text(
                f"💵 Произвольная сумма вывода\n\n"
                f"💰 Доступно: ${balance:.2f}\n\n"
                "Введите сумму в USD (например: 25.5 или 100):\n\n"
                "💸 Минимальная сумма: $5\n"
                "🏦 Максимальная сумма: $5,000\n"
                "📊 Комиссия: 8%",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Назад в меню", callback_data="main_menu")]
                ])
            )
            return

        # ОТМЕНА ПЛАТЕЖНОЙ ОПЕРАЦИИ
        elif data == "payment_cancel":
            logger.info(f"💰 Отмена платежной операции пользователем {user_id}")

            # Просто показываем главное меню
            user_data = bot.db.get_user(user_id)
            if user_data:
                balance = user_data[4]
                username = user_data[1] or user_data[3] or "Игрок"
            else:
                balance = 0.0
                username = "Игрок"

            menu_text = (
                f"🎲 Главное меню\n\n"
                f"👤 {username}\n"
                f"💰 Баланс: ${balance:.2f}\n\n"
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

            await query.edit_message_text(
                text=menu_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return

        # НЕИЗВЕСТНАЯ КНОПКА
        else:
            logger.warning(f"❌ Неизвестная платежная кнопка: {data}")
            await query.answer("❌ Неизвестная команда", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка в payment_callback_handler: {e}")
        await query.answer("❌ Произошла ошибка", show_alert=True)


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def show_deposit_menu(query, bot):
    """Показывает меню депозита"""
    user_id = query.from_user.id
    balance = bot.payment_manager.get_user_balance(user_id)

    keyboard = [
        [InlineKeyboardButton("$10", callback_data="deposit_10")],
        [InlineKeyboardButton("$25", callback_data="deposit_25")],
        [InlineKeyboardButton("$50", callback_data="deposit_50")],
        [InlineKeyboardButton("$100", callback_data="deposit_100")],
        [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💳 **Пополнение баланса**\n\n"
        f"💰 Текущий баланс: ${balance:.2f}\n"
        f"💸 Минимальный депозит: $1\n"
        f"🏦 Максимальный депозит: $10,000\n\n"
        f"Выберите сумму для пополнения:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_withdraw_menu(query, bot):
    """Показывает меню вывода"""
    user_id = query.from_user.id
    balance = bot.payment_manager.get_user_balance(user_id)

    keyboard = [
        [InlineKeyboardButton("$10", callback_data="withdraw_10")],
        [InlineKeyboardButton("$25", callback_data="withdraw_25")],
        [InlineKeyboardButton("$50", callback_data="withdraw_50")],
        [InlineKeyboardButton("$100", callback_data="withdraw_100")],
        [InlineKeyboardButton("💰 Все средства", callback_data="withdraw_all")],
        [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_withdraw")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💸 **Вывод средств**\n\n"
        f"💰 Доступно для вывода: ${balance:.2f}\n"
        f"💸 Минимальная сумма: $5\n"
        f"🏦 Максимальная сумма: $5,000\n"
        f"📊 Комиссия системы: 8%\n\n"
        f"Выберите сумму для вывода:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def process_deposit(query, amount: float, bot, context):
    """Обработка депозита"""
    user_id = query.from_user.id

    payment, pay_url, error = await bot.payment_manager.create_deposit(
        user_id=user_id,
        amount_usd=amount,
        description=f"Депозит от пользователя {user_id}"
    )

    if error:
        await query.answer(f"❌ {error}", show_alert=True)
        return

    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
        [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_deposit_{payment.payment_id}")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"💰 **Счет на оплату создан!**\n\n"
        f"📝 ID платежа: `{payment.payment_id}`\n"
        f"💵 Сумма: ${amount:.2f}\n"
        f"⏳ Срок действия: 1 час\n\n"
        f"Нажмите кнопку ниже для оплаты:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def process_withdraw(query, amount: float, bot, context):
    """Обработка вывода"""
    user_id = query.from_user.id

    payment, error = await bot.payment_manager.create_withdrawal(
        user_id=user_id,
        amount_usd=amount,
        description=f"Вывод средств пользователя {user_id}"
    )

    if error:
        await query.answer(f"❌ {error}", show_alert=True)
        return

    commission = amount * 0.08
    receive_amount = amount - commission

    keyboard = [
        [InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{payment.payment_id}")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✅ **Запрос на вывод создан!**\n\n"
        f"📝 ID заявки: `{payment.payment_id}`\n"
        f"💵 Запрошено: ${amount:.2f}\n"
        f"📊 Комиссия (8%): ${commission:.2f}\n"
        f"💰 К получению: ${receive_amount:.2f}\n\n"
        f"⏳ Обычно обработка занимает 1-24 часа.\n"
        f"Вы можете отменить заявку в течение 10 минут.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def ask_custom_deposit(query, bot):
    """Запрос произвольной суммы депозита"""
    await query.edit_message_text(
        "💵 **Произвольная сумма депозита**\n\n"
        "Введите сумму в USD (например: 15.5 или 75):\n\n"
        "💸 Минимальная сумма: $1\n"
        "🏦 Максимальная сумма: $10,000",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
        ])
    )


async def ask_custom_withdraw(query, bot):
    """Запрос произвольной суммы вывода"""
    user_id = query.from_user.id
    balance = bot.payment_manager.get_user_balance(user_id)

    await query.edit_message_text(
        f"💵 **Произвольная сумма вывода**\n\n"
        f"💰 Доступно: ${balance:.2f}\n\n"
        "Введите сумму в USD (например: 25.5 или 100):\n\n"
        "💸 Минимальная сумма: $5\n"
        "🏦 Максимальная сумма: $5,000\n"
        "📊 Комиссия: 8%",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Назад", callback_data="withdraw")]
        ])
    )


async def check_deposit_status(query, payment_id: str, bot):
    """Проверка статуса депозита"""
    status, error = await bot.payment_manager.check_deposit_status(payment_id)

    if error:
        await query.answer(f"❌ {error}", show_alert=True)
        return

    status_texts = {
        "pending": "⏳ Ожидает оплаты",
        "completed": "✅ Оплачен и зачислен",
        "expired": "❌ Время оплаты истекло",
        "failed": "❌ Ошибка оплаты"
    }

    status_text = status_texts.get(status, f"Статус: {status}")

    keyboard = [[InlineKeyboardButton("🔄 Проверить еще раз", callback_data=f"check_deposit_{payment_id}")]]

    if status == "completed":
        keyboard.append([InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"📊 **Статус платежа:** {status_text}\n\n"
        f"📝 ID платежа: `{payment_id}`",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def cancel_withdrawal(query, payment_id: str, bot, user_id: int):
    """Отмена вывода средств"""
    success, error = await bot.payment_manager.cancel_withdrawal(payment_id, user_id)

    if not success:
        await query.answer(f"❌ {error}", show_alert=True)
        return

    await query.edit_message_text(
        "✅ **Запрос на вывод отменен!**\n\n"
        "💰 Средства возвращены на ваш баланс.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
        ])
    )


async def show_payment_history(query, bot, user_id: int):
    """Показать историю платежей"""
    payments = bot.payment_manager.get_user_payments(user_id, limit=15)

    if not payments:
        await query.edit_message_text(
            "📋 **История платежей пуста**\n\n"
            "У вас еще не было операций по пополнению или выводу средств.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
            ])
        )
        return

    history_text = "📋 **История платежей:**\n\n"

    for i, payment in enumerate(payments, 1):
        payment_id, amount, currency, status, ptype, created_at, desc = payment
        emoji = "📥" if ptype == "deposit" else "📤"
        status_emoji = "✅" if status == "completed" else "⏳" if status == "pending" else "❌"
        date_time = created_at[:16].replace("T", " ")

        short_id = payment_id[:8] + "..."
        history_text += f"{i}. {emoji} {status_emoji} ${amount:.2f}\n"
        history_text += f"   Тип: {ptype} | ID: `{short_id}`\n"
        history_text += f"   Дата: {date_time} | Статус: {status}\n\n"

    keyboard = [
        [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        history_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


# ==================== ОБРАБОТЧИКИ СООБЩЕНИЙ ====================

async def handle_payment_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений для платежей"""
    # Проверяем, что есть сообщение
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    text = update.message.text.strip()

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot:
            return

        # Обработка произвольной суммы депозита
        if context.user_data.get('waiting_for_deposit'):
            del context.user_data['waiting_for_deposit']

            try:
                amount = float(text)
                if amount < 1.0:
                    await update.message.reply_text("❌ Минимальная сумма депозита: $1")
                    return
                if amount > 10000.0:
                    await update.message.reply_text("❌ Максимальная сумма депозита: $10,000")
                    return

                # Создаем депозит
                payment, pay_url, error = await bot.payment_manager.create_deposit(
                    user_id=user.id,
                    amount_usd=amount,
                    description=f"Депозит от {user.first_name}"
                )

                if error:
                    await update.message.reply_text(f"❌ {error}")
                    return

                keyboard = [
                    [InlineKeyboardButton("💳 Оплатить", url=pay_url)],
                    [InlineKeyboardButton("🔄 Проверить статус", callback_data=f"check_deposit_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"💰 **Счет на оплату создан!**\n\n"
                    f"📝 ID платежа: `{payment.payment_id}`\n"
                    f"💵 Сумма: ${amount:.2f}\n"
                    f"⏳ Срок действия: 1 час\n\n"
                    f"Нажмите кнопку ниже для оплаты:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            except ValueError:
                await update.message.reply_text("❌ Пожалуйста, введите корректную сумму (например: 15.5 или 75)")

        # Обработка произвольной суммы вывода
        elif context.user_data.get('waiting_for_withdraw'):
            del context.user_data['waiting_for_withdraw']

            try:
                amount = float(text)
                balance = bot.payment_manager.get_user_balance(user.id)

                if amount < 5.0:
                    await update.message.reply_text("❌ Минимальная сумма вывода: $5")
                    return
                if amount > 5000.0:
                    await update.message.reply_text("❌ Максимальная сумма вывода: $5,000")
                    return
                if amount > balance:
                    await update.message.reply_text(f"❌ Недостаточно средств. Доступно: ${balance:.2f}")
                    return

                # Создаем запрос на вывод
                payment, error = await bot.payment_manager.create_withdrawal(
                    user_id=user.id,
                    amount_usd=amount,
                    description=f"Вывод средств от {user.first_name}"
                )

                if error:
                    await update.message.reply_text(f"❌ {error}")
                    return

                commission = amount * 0.08
                receive_amount = amount - commission

                keyboard = [
                    [InlineKeyboardButton("❌ Отменить вывод", callback_data=f"cancel_withdraw_{payment.payment_id}")],
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"✅ **Запрос на вывод создан!**\n\n"
                    f"📝 ID заявки: `{payment.payment_id}`\n"
                    f"💵 Запрошено: ${amount:.2f}\n"
                    f"📊 Комиссия (8%): ${commission:.2f}\n"
                    f"💰 К получению: ${receive_amount:.2f}\n\n"
                    f"⏳ Обычно обработка занимает 1-24 часа.\n"
                    f"Вы можете отменить заявку в течение 10 минут.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )

            except ValueError:
                await update.message.reply_text("❌ Пожалуйста, введите корректную сумму (например: 25.5 или 100)")

    except Exception as e:
        logger.error(f"Ошибка в handle_payment_message: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке запроса")


# ==================== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ====================

def register_payment_handlers(application, bot):
    """Регистрация обработчиков платежей"""
    from telegram.ext import CommandHandler, MessageHandler, filters

    # Команды
    application.add_handler(CommandHandler("deposit", deposit_command))
    application.add_handler(CommandHandler("withdraw", withdraw_command))
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("payments", balance_command))  # Алиас

    # Callback для платежей
    application.add_handler(CallbackQueryHandler(
        payment_callback_handler,
        pattern=r"^(deposit|withdraw|check_deposit|cancel_withdraw|payment_history|custom_|deposit_|withdraw_)"
    ))

    # Обработчики сообщений для произвольных сумм
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_payment_message
    ))

    logger.info("✅ Обработчики платежей зарегистрированы")

