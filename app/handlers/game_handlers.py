from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from app.handlers.commands import show_main_menu_from_message
import logging
import asyncio

logger = logging.getLogger(__name__)


# ============ ОБРАБОТЧИКИ ИГР 1 НА 1 ============

async def show_bet_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает ввод суммы ставки для игры 1 на 1"""
    query = update.callback_query
    await query.answer()

    # Просим ввести сумму
    await query.edit_message_text(
        "💰 Введите сумму ставки в долларах (минимум: $1, максимум: $1000):\n\n"
        "Пример: 15 (для ставки $15)\n"
        "Или 50.5 (для ставки $50.50)\n\n"
        "❌ Для отмены нажмите /cancel"
    )

    # Устанавливаем состояние ожидания ввода суммы
    context.user_data['waiting_for_bet'] = True
    context.user_data['action'] = 'create_game'


async def handle_bet_and_payment_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод суммы для ставок И платежей"""

    logger.info(f"=" * 50)
    logger.info(f"🔴 ВЫЗВАН ОБРАБОТЧИК ВВОДА!")
    logger.info(f"🔴 Пользователь: {update.effective_user.id}")
    logger.info(f"🔴 Сообщение: '{update.message.text if update.message else 'НЕТ'}'")
    logger.info(f"🔴 user_data: {dict(context.user_data)}")
    logger.info(f"=" * 50)

    # Проверяем, ждем ли мы ввод ставки ИЛИ платежа
    waiting_for_bet = context.user_data.get('waiting_for_bet')
    waiting_for_payment = context.user_data.get('waiting_for_payment')

    logger.info(f"🔍 Результат проверки: bet={waiting_for_bet}, payment={waiting_for_payment}")

    if not waiting_for_bet and not waiting_for_payment:
        logger.info("🔍 Нет ожидающих состояний, выходим")
        return  # Ничего не ждем

    try:
        user_id = update.effective_user.id
        message_text = update.message.text.strip()

        # Проверяем отмену
        if message_text.lower() == '/cancel':
            # Очищаем ВСЕ состояния
            context.user_data.pop('waiting_for_bet', None)
            context.user_data.pop('waiting_for_payment', None)

            logger.info(f"🔍 Отмена операции пользователем {user_id}")

            await update.message.reply_text("❌ Операция отменена")

            # Возвращаем в главное меню
            bot = context.application.bot_data.get('bot_instance')
            if bot:
                from app.handlers.commands import show_main_menu_from_message
                await show_main_menu_from_message(update, bot)
            return

        # Пробуем преобразовать в число
        try:
            amount = float(message_text)
            logger.info(f"🔍 Преобразовано в число: {amount}")
        except ValueError:
            await update.message.reply_text(
                "❌ Пожалуйста, введите число\n\n"
                "Пример: 15 (для $15)\n"
                "Или: 25.5 (для $25.50)\n\n"
                "💵 Введите сумму:"
            )
            return

        # ========== РАЗДЕЛЕНИЕ ЛОГИКИ ==========

        if waiting_for_payment == 'deposit':
            logger.info(f"💰 Обработка ДЕПОЗИТА на сумму ${amount:.2f}")

            # ОБРАБОТКА ДЕПОЗИТА
            if amount < 1:
                await update.message.reply_text("❌ Минимальная сумма: $1\n\n💵 Введите сумму:")
                return

            if amount > 1000:
                await update.message.reply_text("❌ Максимальная сумма: $1000\n\n💵 Введите сумму:")
                return

            # Очищаем состояние
            context.user_data.pop('waiting_for_payment', None)

            # Получаем бота
            bot = context.application.bot_data.get('bot_instance')
            if not bot:
                await update.message.reply_text("❌ Ошибка системы")
                return

            # Пополняем баланс
            bot.db.update_balance(user_id, amount)

            # Получаем новый баланс
            user = bot.db.get_user(user_id)
            new_balance = user[4] if user else amount

            logger.info(f"💰 Баланс пользователя {user_id} пополнен на ${amount:.2f}, новый баланс: ${new_balance:.2f}")

            await update.message.reply_text(
                f"✅ Баланс пополнен на ${amount:.2f}\n"
                f"💰 Новый баланс: ${new_balance:.2f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ])
            )
            return

        elif waiting_for_payment == 'withdraw':
            logger.info(f"💰 Обработка ВЫВОДА на сумму ${amount:.2f}")

            # ОБРАБОТКА ВЫВОДА
            if amount < 1:
                await update.message.reply_text("❌ Минимальная сумма: $1\n\n💵 Введите сумму:")
                return

            # Очищаем состояние
            context.user_data.pop('waiting_for_payment', None)

            # Получаем бота
            bot = context.application.bot_data.get('bot_instance')
            if not bot:
                await update.message.reply_text("❌ Ошибка системы")
                return

            # Проверяем баланс
            user = bot.db.get_user(user_id)
            if not user:
                await update.message.reply_text("❌ Пользователь не найден")
                return

            current_balance = user[4]

            if current_balance < amount:
                await update.message.reply_text(
                    f"❌ Недостаточно средств!\n"
                    f"Ваш баланс: ${current_balance:.2f}\n"
                    f"Требуется: ${amount:.2f}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                    ])
                )
                return

            # Списываем средства
            bot.db.update_balance(user_id, -amount)

            # Создаем запись о выводе
            try:
                # Коммитим любые ожидающие транзакции
                bot.db.get_connection().commit()

                cursor = bot.db.get_connection().cursor()

                # ВАЖНО: добавляем created_at
                cursor.execute("""
                    INSERT INTO payments (user_id, amount, payment_type, status, description, created_at)
                    VALUES (?, ?, 'withdraw', 'pending', ?, datetime('now'))
                """, (user_id, amount, f"Запрос на вывод ${amount:.2f}"))

                bot.db.get_connection().commit()

                payment_id = cursor.lastrowid
                cursor.close()

                logger.info(f"💰 Создана заявка на вывод ID: {payment_id}")

            except Exception as e:
                logger.error(f"Ошибка создания записи о выводе: {e}")

                # Пробуем вернуть средства
                try:
                    bot.db.get_connection().commit()
                    bot.db.update_balance(user_id, amount)
                    bot.db.get_connection().commit()
                except Exception as e2:
                    logger.error(f"Ошибка возврата средств: {e2}")

                await update.message.reply_text(
                    "❌ Ошибка создания заявки. Средства возвращены на баланс.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                    ])
                )
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
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ]),
                parse_mode='Markdown'
            )

            logger.info(f"💸 Вывод: пользователь {user_id} запросил вывод ${amount:.2f}, ID заявки: {payment_id}")
            return

        elif waiting_for_bet:
            logger.info(f"🎲 Обработка СТАВКИ на сумму ${amount:.2f}")

            # ОРИГИНАЛЬНАЯ ЛОГИКА ДЛЯ СТАВОК
            # Проверяем минимальную и максимальную сумму
            if amount < 1:
                await update.message.reply_text("❌ Минимальная ставка: $1\n\n💰 Введите сумму ставки:")
                return

            if amount > 1000:
                await update.message.reply_text("❌ Максимальная ставка: $1000\n\n💰 Введите сумму ставки:")
                return

            # Очищаем состояние
            context.user_data.pop('waiting_for_bet', None)

            # Создаем игру
            bot = context.application.bot_data.get('bot_instance')
            if not bot or not hasattr(bot, 'game_manager'):
                await update.message.reply_text("❌ Ошибка: система игр не инициализирована")
                return

            game_manager = bot.game_manager
            user_name = update.effective_user.username or update.effective_user.first_name

            # Создаем игру
            game, error = game_manager.create_game(
                creator_id=user_id,
                creator_name=user_name,
                bet_amount=amount
            )

            if error:
                await update.message.reply_text(f"❌ {error}")
                return

            # Инициализируем хранилище message_id если нужно
            if not hasattr(game_manager, 'game_messages'):
                game_manager.game_messages = {}

            if game.id not in game_manager.game_messages:
                game_manager.game_messages[game.id] = []

            # Клавиатура для создателя
            keyboard = [
                [InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game.id}")],
                [InlineKeyboardButton("❌ Отменить игру", callback_data=f"cancel_active_game_{game.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Сообщение создателю
            game_message_text = (
                f"🎲 Игра создана!\n"
                f"💰 Ставка: ${game.bet_amount:.2f}\n\n"
                f"🆔 Код игры: `{game.game_code}`\n\n"
                "📤 **Отправьте следующее сообщение другу!**"
            )

            game_message = await update.message.reply_text(
                game_message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

            # Сохраняем ID этого сообщения
            game_msg_data = {
                "chat_id": update.message.chat_id,
                "message_id": game_message.message_id
            }
            logger.info(f"🔍 СООБЩЕНИЕ ОБ ИГРЕ: {game_msg_data}")
            if game_msg_data not in game_manager.game_messages[game.id]:
                game_manager.game_messages[game.id].append(game_msg_data)

            # Отправляем приглашение для пересылки
            await send_game_invite_from_message(update, game, context)

    except Exception as e:
        logger.error(f"❌ Ошибка обработки ввода: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def send_game_invite_from_message(update: Update, game, context):
    """Отправляет приглашение для присоединения к игре (версия для текстового сообщения)"""
    try:
        # Получаем username бота
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        # Создаем глубокую ссылку для ПРИСОЕДИНЕНИЯ
        deep_link_url = f"https://t.me/{bot_username}?start=join_{game.game_code}"

        invite_text = (
            f"🎲 **Приглашение в игру!**\n\n"
            f"💰 Ставка: ${game.bet_amount:.2f}\n"
            f"🎯 Формат: 1 на 1\n"
            f"🆔 Код: `{game.game_code}`\n\n"
            f"🎯 [Присоединиться к игре]({deep_link_url})\n\n"
            f"💰 *Победитель забирает ${game.bet_amount * 2 * 0.92:.2f} (за вычетом комиссии 8%)*"
        )

        keyboard = [
            [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ", url=deep_link_url)],
            [InlineKeyboardButton("📋 Или используй команду", callback_data=f"copy_{game.game_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        invite_message = await update.message.reply_text(
            invite_text,
            parse_mode='Markdown',
            disable_web_page_preview=False,
            reply_markup=reply_markup
        )

        # Сохраняем ID сообщения приглашения
        bot = context.application.bot_data.get('bot_instance')
        if bot and hasattr(bot, 'game_manager'):
            game_manager = bot.game_manager
            if game.id in game_manager.game_messages:
                invite_msg_data = {
                    "chat_id": invite_message.chat_id,
                    "message_id": invite_message.message_id
                }
                if invite_msg_data not in game_manager.game_messages[game.id]:
                    game_manager.game_messages[game.id].append(invite_msg_data)

        return invite_message

    except Exception as e:
        logger.error(f"Ошибка отправки приглашения: {e}")
        # Запасной вариант
        try:
            fallback_message = await update.message.reply_text(
                f"🎲 Приглашение в игру!\n\n"
                f"💰 Ставка: ${game.bet_amount:.2f}\n"
                f"🎯 Формат: 1 на 1\n"
                f"🆔 Код: {game.game_code}\n\n"
                f"Используйте команду: /join {game.game_code}"
            )
            return fallback_message
        except:
            return None


async def handle_dice_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает бросок костей в игре"""
    query = update.callback_query
    await query.answer()

    try:
        # Получаем менеджер
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'game_manager'):
            await query.answer("❌ Система игр не инициализирована", show_alert=True)
            return

        game_manager = bot.game_manager

        # Извлекаем ID игры
        game_id = int(query.data.split("_")[1])

        # Отправляем анимированные кости
        dice_message = await query.message.reply_dice(emoji="🎲")
        dice_value = dice_message.dice.value

        # Ждем анимацию
        await asyncio.sleep(3)

        # Обрабатываем бросок
        game, error = await game_manager.process_dice_roll(
            game_id=game_id,
            player_id=query.from_user.id,
            dice_value=dice_value
        )

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        # Формируем сообщение с результатом
        if query.from_user.id == game.player1_id:
            current_rolls = game.player1_rolls
            player_name = game.player1_name
        else:
            current_rolls = game.player2_rolls
            player_name = game.player2_name

        rolls_count = len(current_rolls)
        total_so_far = sum(current_rolls)

        message_text = (
            f"🎯 {player_name} - бросок {rolls_count}/3\n"
            f"🎲 Выпало: {dice_value}\n\n"
            f"📊 Ваши броски: {', '.join(map(str, current_rolls))}\n"
            f"💰 Сумма: {total_so_far}\n"
        )

        if rolls_count < 3:
            # Еще есть броски
            message_text += f"\nОсталось бросков: {3 - rolls_count}"
            keyboard = [[InlineKeyboardButton("🎲 Бросить снова", callback_data=f"roll_{game_id}")]]
        else:
            # Игрок завершил все броски
            message_text += "\n✅ Вы завершили все броски!"
            keyboard = [[InlineKeyboardButton("⏳ Ожидаем соперника", callback_data="waiting")]]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(message_text, reply_markup=reply_markup)

        # Если оба игрока завершили
        if game.status == "finished":
            await process_game_result(game, context, bot)

    except Exception as e:
        logger.error(f"Ошибка броска костей: {e}")
        await query.answer(f"❌ Ошибка броска: {str(e)}", show_alert=True)


async def cancel_active_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет активную игру и удаляет все сообщения"""
    query = update.callback_query
    await query.answer()

    try:
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'game_manager'):
            await query.answer("❌ Система игр не инициализирована", show_alert=True)
            return

        game_manager = bot.game_manager
        game_id = int(query.data.split("_")[3])
        user_id = query.from_user.id

        # Пробуем отменить через менеджер
        success, error = await game_manager.cancel_game(
            game_id=game_id,
            user_id=user_id,
            context=context
        )

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        await query.answer("✅ Игра отменена. Все сообщения удалены.", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены игры: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отмены игры: {e}")
        await query.answer(f"❌ Ошибка: {str(e)[:50]}", show_alert=True)


async def join_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /join <код> - присоединение к игре"""
    try:
        if not context.args:
            await update.message.reply_text(
                "Использование: /join <КОД_ИГРЫ>\n\n"
                "Пример: `/join A1B2C3`",
                parse_mode='Markdown'
            )
            return

        game_code = context.args[0].upper()
        user_id = update.effective_user.id
        user_name = update.effective_user.username or update.effective_user.first_name

        # Получаем менеджер
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'game_manager'):
            await update.message.reply_text("❌ Система игр не инициализирована")
            return

        game_manager = bot.game_manager

        # Присоединяемся к игре
        game, error = game_manager.join_game(game_code, user_id, user_name)

        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        # Отправляем сообщение о присоединении
        keyboard = [[InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Вы присоединились к игре {game.game_code}!\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n"
            f"🎲 Готовы бросить кости?",
            reply_markup=reply_markup
        )

        # Уведомляем создателя игры
        try:
            await context.bot.send_message(
                chat_id=game.player1_id,
                text=f"✅ Игрок {user_name} присоединился к вашей игре {game.game_code}!",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления создателя: {e}")

    except Exception as e:
        logger.error(f"Ошибка присоединения к игре: {e}")
        await update.message.reply_text(f"❌ Ошибка присоединения: {str(e)}")


async def send_game_invite(query, game, context):
    """Отправляет приглашение для присоединения к игре"""
    try:
        # Получаем username бота
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        # Создаем глубокую ссылку для ПРИСОЕДИНЕНИЯ
        deep_link_url = f"https://t.me/{bot_username}?start=join_{game.game_code}"

        invite_text = (
            f"🎲 **Приглашение в игру!**\n\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n"
            f"🎯 Формат: 1 на 1\n"
            f"🆔 Код: `{game.game_code}`\n\n"
            f"🎯 [Присоединиться к игре]({deep_link_url})\n\n"  # <-- ВОТ ССЫЛКА В ТЕКСТЕ!
            f"💰 *Победитель забирает ${game.bet_amount * 2 * 0.92:.0f} (за вычетом комиссии 8%)*"
        )

        keyboard = [
            [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ", url=deep_link_url)],
            [InlineKeyboardButton("📋 Или используй команду", callback_data=f"copy_{game.game_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        invite_message = await query.message.reply_text(
            invite_text,
            parse_mode='Markdown',
            disable_web_page_preview=False,  # <-- Разрешаем превью ссылки
            reply_markup=reply_markup
        )

        return invite_message

    except Exception as e:
        logger.error(f"Ошибка отправки приглашения: {e}")
        # Запасной вариант
        try:
            fallback_message = await query.message.reply_text(
                f"🎲 Приглашение в игру!\n\n"
                f"💰 Ставка: ${game.bet_amount:.0f}\n"
                f"🎯 Формат: 1 на 1\n"
                f"🆔 Код: {game.game_code}\n\n"
                f"Используйте команду: /join {game.game_code}"
            )
            return fallback_message
        except:
            return None


async def process_game_result(game, context, bot=None):  # ← ДОБАВЛЯЕМ bot
    """Обрабатывает результат завершенной игры"""
    try:
        # Получаем бота из context если не передали
        if not bot:
            bot = context.application.bot_data.get('bot_instance')

        if not bot:
            logger.error("Бот не найден в контексте")
            return

        # Общий банк и комиссия
        total_bank = game.bet_amount * 2
        commission = total_bank * 0.08
        winner_amount = total_bank - commission

        if game.winner_id:
            winner_name = game.player1_name if game.winner_id == game.player1_id else game.player2_name
            loser_name = game.player2_name if game.winner_id == game.player1_id else game.player1_name

            # Уведомляем победителя
            winner_text = (
                f"🏆 Поздравляем с победой!\n"
                f"💰 Ваш выигрыш: ${winner_amount:.2f}\n"
                f"🎮 Противник: {loser_name}"
            )

            # Уведомляем проигравшего
            loser_text = (
                f"😔 Вы проиграли\n"
                f"💰 Потеряно: ${game.bet_amount:.2f}\n"
                f"🎮 Победитель: {winner_name}"
            )

            await context.bot.send_message(chat_id=game.winner_id, text=winner_text)
            await context.bot.send_message(
                chat_id=game.player2_id if game.winner_id == game.player1_id else game.player1_id,
                text=loser_text
            )

            # Создаем выплату через payment_manager (если он есть)
            if hasattr(bot, 'payment_manager') and bot.payment_manager:
                try:
                    payment, error = await bot.payment_manager.create_withdrawal(
                        user_id=game.winner_id,
                        amount_usd=winner_amount,
                        description=f"Выигрыш в игре #{game.game_code}"
                    )

                    if payment:
                        logger.info(f"✅ Чек создан для победителя {winner_name}: ${winner_amount:.2f}")
                        await context.bot.send_message(
                            chat_id=game.winner_id,
                            text=f"💰 Чек на ${winner_amount:.2f} создан! Ожидайте выплаты."
                        )
                    else:
                        logger.error(f"❌ Ошибка создания чека: {error}")
                        # Альтернатива: зачисляем на баланс
                        bot.db.update_balance(game.winner_id, winner_amount)
                except Exception as e:
                    logger.error(f"❌ Ошибка payment_manager: {e}")
                    # Запасной вариант
                    bot.db.update_balance(game.winner_id, winner_amount)
            else:
                # Если нет payment_manager, просто обновляем баланс
                bot.db.update_balance(game.winner_id, winner_amount)
                logger.info(f"⚠️ PaymentManager не доступен, баланс обновлен")
        else:
            # Ничья - возвращаем ставки
            bot.db.update_balance(game.player1_id, game.bet_amount)
            bot.db.update_balance(game.player2_id, game.bet_amount)

            draw_text = "🤝 Ничья! Ставки возвращены."
            await context.bot.send_message(chat_id=game.player1_id, text=draw_text)
            await context.bot.send_message(chat_id=game.player2_id, text=draw_text)

        logger.info(f"🎮 Игра {game.id} завершена. Победитель: {game.winner_id}")

    except Exception as e:
        logger.error(f"❌ Ошибка обработки результата: {e}")


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /cancel"""
    # Проверяем, находимся ли мы в состоянии ожидания ставки
    if context.user_data.get('waiting_for_bet'):
        # Очищаем состояние
        context.user_data.pop('waiting_for_bet', None)
        context.user_data.pop('action', None)

        await update.message.reply_text("✅ Создание игры отменено")

        # Пытаемся вернуть в главное меню
        try:
            from app.handlers.commands import show_main_menu_from_message
            bot = context.application.bot_data.get('bot_instance')
            if bot:
                await show_main_menu_from_message(update, bot)
        except Exception as e:
            logger.error(f"Ошибка возврата в меню: {e}")
            # Если не получилось - просто отправляем текст
            await update.message.reply_text("Используйте /start для возврата в меню")
    else:
        # Не в состоянии ожидания
        await update.message.reply_text("ℹ️ Нечего отменять")


async def send_game_invite_from_message(update: Update, game, context):
    """Отправляет приглашение для присоединения к игре (версия для текстового сообщения)"""
    try:
        # Получаем username бота
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        # Создаем глубокую ссылку для ПРИСОЕДИНЕНИЯ
        deep_link_url = f"https://t.me/{bot_username}?start=join_{game.game_code}"

        invite_text = (
            f"🎲 **Приглашение в игру!**\n\n"
            f"💰 Ставка: ${game.bet_amount:.2f}\n"
            f"🎯 Формат: 1 на 1\n"
            f"🆔 Код: `{game.game_code}`\n\n"
            f"🎯 [Присоединиться к игре]({deep_link_url})\n\n"
            f"💰 *Победитель забирает ${game.bet_amount * 2 * 0.92:.2f} (за вычетом комиссии 8%)*"
        )

        keyboard = [
            [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ", url=deep_link_url)],
            [InlineKeyboardButton("📋 Или используй команду", callback_data=f"copy_{game.game_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        invite_message = await update.message.reply_text(
            invite_text,
            parse_mode='Markdown',
            disable_web_page_preview=False,
            reply_markup=reply_markup
        )

        # Сохраняем ID сообщения приглашения
        bot = context.application.bot_data.get('bot_instance')
        if bot and hasattr(bot, 'game_manager'):
            game_manager = bot.game_manager
            if game.id in game_manager.game_messages:
                invite_msg_data = {
                    "chat_id": invite_message.chat_id,
                    "message_id": invite_message.message_id
                }
                if invite_msg_data not in game_manager.game_messages[game.id]:
                    game_manager.game_messages[game.id].append(invite_msg_data)

        return invite_message

    except Exception as e:
        logger.error(f"Ошибка отправки приглашения: {e}")
        # Запасной вариант
        try:
            fallback_message = await update.message.reply_text(
                f"🎲 Приглашение в игру!\n\n"
                f"💰 Ставка: ${game.bet_amount:.2f}\n"
                f"🎯 Формат: 1 на 1\n"
                f"🆔 Код: {game.game_code}\n\n"
                f"Используйте команду: /join {game.game_code}"
            )
            return fallback_message
        except:
            return None


# ============ РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ============

def register_game_handlers(application, bot):
    """Регистрирует обработчики игр в приложении"""
    # Сохраняем ссылку на бота в application context
    application.bot_data['bot_instance'] = bot

    # Callback handlers
    application.add_handler(CallbackQueryHandler(show_bet_options, pattern=r"^find_game$"))
    application.add_handler(CallbackQueryHandler(handle_dice_roll, pattern=r"^roll_"))
    application.add_handler(CallbackQueryHandler(cancel_active_game, pattern=r"^cancel_active_game_"))

    # Command handlers - ВАЖНО: регистрируем ДО MessageHandler!
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("join", join_game_command))

    # Текстовый обработчик для ввода ставки И платежей
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_bet_and_payment_input  # Изменили название функции!
    ))

    logger.info("✅ Обработчики игр 1 на 1 зарегистрированы")

