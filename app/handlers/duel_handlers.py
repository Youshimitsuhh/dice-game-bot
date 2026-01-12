# app/handlers/duel_handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
import logging
import asyncio
import re

logger = logging.getLogger(__name__)


# ============ ОБРАБОТЧИКИ ДУЭЛЕЙ В ГРУППАХ ============

async def duel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /duel <ставка> или /duel @username <ставка>
    Создает дуэль в групповом чате
    """
    chat = update.effective_chat
    user = update.effective_user

    # Проверяем, что команда в группе
    if chat.type not in ["group", "supergroup"]:
        await update.message.reply_text(
            "⚔ Дуэли доступны только в групповых чатах!\n\n"
            "Создайте группу с друзьями или присоединитесь к существующей."
        )
        return

    # Проверяем аргументы
    if not context.args:
        await update.message.reply_text(
            "Использование:\n"
            "`/duel 10` - создать открытую дуэль на 10$\n"
            "`/duel @username 10` - вызвать конкретного игрока\n\n"
            "Пример: `/duel 25` или `/duel @username 50`",
            parse_mode='Markdown'
        )
        return

    # Парсим аргументы
    args = context.args

    # Вариант 1: /duel @username <ставка>
    if len(args) >= 2 and args[0].startswith('@'):
        target_username = args[0][1:]  # Убираем @
        try:
            bet_amount = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Неверная сумма ставки")
            return

        await create_targeted_duel(update, context, target_username, bet_amount)
        return

    # Вариант 2: /duel <ставка> (открытая дуэль)
    try:
        bet_amount = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверная сумма ставки")
        return

    await create_open_duel(update, context, bet_amount)


async def create_open_duel(update: Update, context: ContextTypes.DEFAULT_TYPE, bet_amount: float):
    """Создает открытую дуэль (любой может принять)"""
    chat = update.effective_chat
    user = update.effective_user

    try:
        # Получаем менеджер
        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'duel_manager'):
            await update.message.reply_text("❌ Система дуэлей не инициализирована")
            return

        duel_manager = bot.duel_manager

        # Создаем дуэль
        duel, error = duel_manager.create_duel(
            chat_id=chat.id,
            creator_id=user.id,
            creator_name=user.username or user.first_name,
            bet_amount=bet_amount
        )

        if error:
            await update.message.reply_text(f"❌ {error}")
            return

        # Создаем сообщение с дуэлью
        keyboard = [
            [InlineKeyboardButton("⚔ ПРИНЯТЬ ДУЭЛЬ", callback_data=f"duel_accept_{duel.duel_id}")],
            [InlineKeyboardButton("❌ ОТМЕНИТЬ", callback_data=f"duel_cancel_{duel.duel_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        message = await update.message.reply_text(
            f"⚔ ОТКРЫТАЯ ДУЭЛЬ!\n\n"
            f"🎯 {user.first_name} вызывает любого на дуэль!\n"
            f"💰 Ставка: ${bet_amount:.0f}\n\n"
            f"Первый принявший получает вызов!\n"
            f"Дуэль ID: {duel.duel_id}",
            reply_markup=reply_markup,
        )

        # Сохраняем ID сообщения
        duel.message_id = message.message_id

    except Exception as e:
        logger.error(f"Ошибка создания открытой дуэли: {e}")
        await update.message.reply_text(f"❌ Ошибка создания дуэли: {str(e)}")


async def create_targeted_duel(update: Update, context: ContextTypes.DEFAULT_TYPE,
                               target_username: str, bet_amount: float):
    """Создает дуэль с конкретным игроком"""
    chat = update.effective_chat
    user = update.effective_user

    try:
        # Ищем пользователя в чате (упрощенно - по username)
        # В реальном боте нужно получать user_id через API

        keyboard = [
            [InlineKeyboardButton("⚔ ПРИНЯТЬ ВЫЗОВ", callback_data=f"duel_accept_target_{bet_amount}")],
            [InlineKeyboardButton("🏃 ОТКЛОНИТЬ", callback_data="duel_decline")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚔ ВЫЗОВ НА ДУЭЛЬ!\n\n"
            f"🎯 {user.first_name} вызывает @{target_username}!\n"
            f"💰 Ставка: ${bet_amount:.0f}\n\n"
            f"@{target_username}, принимаешь вызов?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Ошибка создания целевой дуэли: {e}")
        await update.message.reply_text(f"❌ Ошибка создания дуэли: {str(e)}")


async def handle_duel_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка принятия дуэли"""
    query = update.callback_query
    print(f"🔥 DEBUG: Duel accept called! data={query.data}")
    await query.answer()

    try:
        parts = query.data.split("_")
        if len(parts) < 3:
            await query.answer("❌ Неверный формат callback", show_alert=True)
            return

        duel_id = parts[2]

        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'duel_manager'):
            await query.edit_message_text("❌ Система дуэлей не инициализирована")
            return

        duel_manager = bot.duel_manager

        # Принимаем дуэль
        duel, error = duel_manager.accept_duel(
            duel_id=duel_id,
            opponent_id=query.from_user.id,
            opponent_name=query.from_user.username or query.from_user.first_name
        )

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        # Обновляем сообщение - УБРАЛИ parse_mode='Markdown'
        new_text = (
            f"⚔ ДУЭЛЬ ПРИНЯТА!\n\n"
            f"🎯 {duel.creator_name} vs {duel.opponent_name}\n"
            f"💰 Ставка: ${duel.bet_amount:.0f}\n"
            f"🏆 Победитель забирает: ${duel.bet_amount * 2 * 0.92:.0f}\n\n"
            f"🎲 Первым бросает {duel.creator_name}!"
        )

        await query.edit_message_text(
            text=new_text,
            # УБРАЛИ parse_mode='Markdown' - используем обычный текст
        )

        # Отправляем кнопку для первого броска
        keyboard = [[
            InlineKeyboardButton(
                f"🎲 {duel.creator_name} - БРОСИТЬ КОСТИ",
                callback_data=f"duel_roll_{duel.duel_id}_{duel.creator_id}"
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            f"🎲 НАЧАЛО ДУЭЛИ!\n"
            f"У каждого игрока по 3 броска.\n"
            f"Суммируются все выпавшие значения.",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Ошибка принятия дуэли: {e}")
        await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


async def handle_duel_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка броска в дуэли"""
    query = update.callback_query
    await query.answer()

    try:
        # Формат: duel_roll_DUELID_PLAYERID
        parts = query.data.split("_")
        duel_id = parts[2]
        player_id = int(parts[3])

        # Проверяем, что бросает правильный игрок
        if query.from_user.id != player_id:
            await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
            return

        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'duel_manager'):
            await query.answer("❌ Система дуэлей не инициализирована", show_alert=True)
            return

        duel_manager = bot.duel_manager

        # Отправляем анимированные кости
        dice_message = await query.message.reply_dice(emoji="🎲")
        dice_value = dice_message.dice.value

        # Ждем анимацию
        await asyncio.sleep(3)

        # Обрабатываем бросок
        duel, error = duel_manager.process_duel_roll(duel_id, player_id, dice_value)

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        # Получаем информацию о текущем состоянии
        player_name = duel.get_player_name(player_id)
        opponent_id = duel.get_opponent_id(player_id)
        opponent_name = duel.get_player_name(opponent_id) if opponent_id else None

        if player_id == duel.creator_id:
            current_rolls = duel.creator_rolls
            current_total = duel.creator_total
        else:
            current_rolls = duel.opponent_rolls
            current_total = duel.opponent_total

        rolls_count = len(current_rolls)

        # Формируем сообщение о результате
        result_text = (
            f"🎲 {player_name} - бросок {rolls_count}/3\n"
            f"🎯 Выпало: {dice_value}\n"
            f"📊 Броски: {', '.join(map(str, current_rolls))}\n"
            f"💰 Сумма: {current_total}\n\n"
        )

        # Проверяем состояние дуэли
        if duel.status == "finished":
            # Дуэль завершена
            await process_duel_result(duel, query.message.chat_id, context)
            return

        elif duel.is_player_finished(player_id):
            # Игрок завершил все броски
            result_text += f"✅ {player_name} завершил все броски!\n"

            if duel.is_player_finished(opponent_id):
                # Оба завершили, но еще не обработано
                result_text += f"✅ {opponent_name} тоже завершил!\n"
            else:
                # Передаем ход оппоненту
                result_text += f"➡️ Теперь ходит {opponent_name}"

                keyboard = [[
                    InlineKeyboardButton(
                        f"🎲 {opponent_name} - БРОСИТЬ КОСТИ",
                        callback_data=f"duel_roll_{duel.duel_id}_{opponent_id}"
                    )
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.message.reply_text(result_text, reply_markup=reply_markup)
                return

        else:
            # Игрок еще не завершил
            result_text += f"🎲 Осталось бросков: {3 - rolls_count}"

            keyboard = [[
                InlineKeyboardButton(
                    f"🎲 {player_name} - БРОСИТЬ СНОВА",
                    callback_data=f"duel_roll_{duel.duel_id}_{player_id}"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(result_text, reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка броска в дуэли: {e}")
        await query.answer(f"❌ Ошибка броска: {str(e)}", show_alert=True)


async def handle_duel_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена дуэли"""
    query = update.callback_query
    await query.answer()

    try:
        duel_id = query.data.split("_")[2]

        bot = context.application.bot_data.get('bot_instance')
        if not bot or not hasattr(bot, 'duel_manager'):
            await query.edit_message_text("❌ Система дуэлей не инициализирована")
            return

        duel_manager = bot.duel_manager

        success, error = duel_manager.cancel_duel(duel_id, query.from_user.id)

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        await query.edit_message_text(
            "❌ Дуэль отменена создателем.\n"
            "💰 Ставка возвращена на баланс."
        )

    except Exception as e:
        logger.error(f"Ошибка отмены дуэли: {e}")
        await query.answer(f"❌ Ошибка отмены: {str(e)}", show_alert=True)


async def process_duel_result(duel, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает результат завершенной дуэли"""
    try:
        result_text = (
            f"🏆 ДУЭЛЬ ЗАВЕРШЕНА!\n\n"
            f"🎯 {duel.creator_name}: {duel.creator_total} очков\n"
            f"🎯 {duel.opponent_name}: {duel.opponent_total} очков\n\n"
        )

        if duel.winner_id:
            winner_name = duel.creator_name if duel.winner_id == duel.creator_id else duel.opponent_name
            result_text += f"🏆 ПОБЕДИТЕЛЬ: {winner_name}!\n"
            result_text += f"💰 Выигрыш: ${duel.bet_amount * 2 * 0.92:.0f}\n"
        else:
            result_text += "🤝 НИЧЬЯ!\n"
            result_text += "💰 Ставки возвращены обоим игрокам\n"

        result_text += f"\n📅 Дуэль ID: `{duel.duel_id}`"

        # Отправляем результат в чат
        await context.bot.send_message(
            chat_id=chat_id,
            text=result_text,
            parse_mode='Markdown'
        )

        # TODO: Обработка выплат через crypto_pay

    except Exception as e:
        logger.error(f"Ошибка обработки результата дуэли: {e}")


# ============ РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ============

# ============ РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ============

def register_duel_handlers(application, bot):
    """Регистрирует обработчики дуэлей в приложении"""
    # Сохраняем ссылку на бота
    application.bot_data['bot_instance'] = bot

    # Callback handlers С ФИЛЬТРАЦИЕЙ!
    from telegram.ext import CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(
        handle_duel_accept,
        pattern="^duel_accept_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_duel_roll,
        pattern="^duel_roll_"
    ))
    application.add_handler(CallbackQueryHandler(
        handle_duel_cancel,
        pattern="^duel_cancel_"
    ))

    logger.info("✅ Обработчики дуэлей зарегистрированы с фильтрацией")
