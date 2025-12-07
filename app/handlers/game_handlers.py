from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
import logging

logger = logging.getLogger(__name__)


# ============ ОБРАБОТЧИКИ ИГР 1 НА 1 ============

async def show_bet_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает выбор ставки для игры 1 на 1"""
    query = update.callback_query
    await query.answer()

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

    await query.edit_message_text(
        "🎯 Выберите сумму ставки для игры 1 на 1:",
        reply_markup=reply_markup
    )


async def create_pvp_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает игру с выбранной ставкой"""
    query = update.callback_query
    await query.answer()

    try:
        # Получаем менеджер из контекста
        game_manager = context.application.context_data.get('game_manager')
        if not game_manager:
            await query.edit_message_text("❌ Ошибка: менеджер игр не инициализирован")
            return

        # Извлекаем сумму ставки
        bet_amount = float(query.data.split("_")[1])

        # Создаем игру
        game, error = game_manager.create_game(
            creator_id=query.from_user.id,
            creator_name=query.from_user.username or query.from_user.first_name,
            bet_amount=bet_amount
        )

        if error:
            await query.edit_message_text(
                f"❌ {error}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
                ])
            )
            return

        # Клавиатура для создателя
        keyboard = [
            [InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game.id}")],
            [InlineKeyboardButton("❌ Отменить игру", callback_data=f"cancel_active_game_{game.id}")],
            [InlineKeyboardButton("📋 Показать команду", callback_data=f"copy_{game.id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Сообщение создателю
        await query.edit_message_text(
            f"🎲 Игра создана!\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n\n"
            f"🆔 Код игры: `{game.game_code}`\n\n"
            "📤 **Отправьте приглашение другу!**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Отправляем приглашение для пересылки
        await send_game_invite(query, game, context)

    except Exception as e:
        logger.error(f"Ошибка создания игры: {e}")
        await query.edit_message_text(
            f"❌ Ошибка создания игры: {str(e)}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
            ])
        )


async def handle_dice_roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает бросок костей в игре"""
    query = update.callback_query
    await query.answer()

    try:
        game_manager = context.application.context_data.get('game_manager')
        if not game_manager:
            await query.answer("❌ Менеджер игр не инициализирован", show_alert=True)
            return

        # Извлекаем ID игры
        game_id = int(query.data.split("_")[1])

        # Отправляем анимированные кости
        dice_message = await query.message.reply_dice(emoji="🎲")
        dice_value = dice_message.dice.value

        # Ждем анимацию
        import asyncio
        await asyncio.sleep(3)

        # Обрабатываем бросок
        game, error = game_manager.process_dice_roll(
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
        else:
            current_rolls = game.player2_rolls

        rolls_count = len(current_rolls)
        total_so_far = sum(current_rolls)

        message_text = (
            f"🎯 Бросок {rolls_count}/3\n"
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
            await process_game_result(game, context)

    except Exception as e:
        logger.error(f"Ошибка броска костей: {e}")
        await query.answer(f"❌ Ошибка броска: {str(e)}", show_alert=True)


async def cancel_active_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет активную игру"""
    query = update.callback_query
    await query.answer()

    try:
        game_manager = context.application.context_data.get('game_manager')
        if not game_manager:
            await query.answer("❌ Менеджер игр не инициализирован", show_alert=True)
            return

        game_id = int(query.data.split("_")[3])

        success, error = game_manager.cancel_game(
            game_id=game_id,
            user_id=query.from_user.id
        )

        if error:
            await query.answer(f"❌ {error}", show_alert=True)
            return

        await query.edit_message_text(
            "✅ Игра отменена. Средства возвращены на баланс.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка отмены игры: {e}")
        await query.answer(f"❌ Ошибка отмены: {str(e)}", show_alert=True)


async def send_game_invite(query, game, context):
    """Отправляет приглашение для присоединения к игре"""
    try:
        # Получаем username бота
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username

        # Создаем глубокую ссылку
        deep_link_url = f"https://t.me/{bot_username}?start=join_{game.game_code}"

        invite_text = (
            f"🎲 **Приглашение в игру!**\n\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n"
            f"🎯 Формат: 1 на 1\n"
            f"🆔 Код: `{game.game_code}`\n\n"
            f"🎯 [Присоединиться к игре]({deep_link_url})\n\n"
            f"💰 *Победитель забирает ${game.bet_amount * 2 * 0.92:.0f} (за вычетом комиссии 8%)*"
        )

        instruction_text = (
            f"📤 **Отправьте это сообщение другу!**\n\n"
            f"Просто перешлите сообщение ниже - друг сможет присоединиться по ссылке."
        )

        await query.message.reply_text(instruction_text, parse_mode='Markdown')
        await query.message.reply_text(
            invite_text,
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ", url=deep_link_url)],
                [InlineKeyboardButton("📋 Или используй команду", callback_data="show_command")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка отправки приглашения: {e}")
        # Запасной вариант
        await query.message.reply_text(
            f"🎲 Приглашение в игру!\n\n"
            f"💰 Ставка: ${game.bet_amount:.0f}\n"
            f"🎯 Формат: 1 на 1\n"
            f"🆔 Код: {game.game_code}\n\n"
            f"Используйте команду: /join {game.game_code}"
        )


async def process_game_result(game, context):
    """Обрабатывает результат завершенной игры"""
    # TODO: Реализовать логику выплат
    pass


# ============ РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ ============

def register_game_handlers(application):
    """Регистрирует обработчики игр в приложении"""
    # Callback handlers
    application.add_handler(CallbackQueryHandler(show_bet_options, pattern=r"^find_game$"))
    application.add_handler(CallbackQueryHandler(create_pvp_game, pattern=r"^bet_"))
    application.add_handler(CallbackQueryHandler(handle_dice_roll, pattern=r"^roll_"))
    application.add_handler(CallbackQueryHandler(cancel_active_game, pattern=r"^cancel_active_game_"))

    # Command handlers
    # application.add_handler(CommandHandler("join", join_game_command))

    logger.info("Обработчики игр 1 на 1 зарегистрированы")


async def join_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /join <код>"""
    # TODO: Реализовать команду присоединения
    pass


