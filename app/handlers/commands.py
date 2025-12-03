# app/handlers/commands.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
import logging

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
    """Обработчик команды /start - ПЕРВАЯ ВЕРСИЯ (упрощенная)"""
    user = update.effective_user
    chat = update.effective_chat

    logger.info(f"👤 /start от {user.id} ({user.username}) в чате {chat.type}")

    # Пока упрощаем - просто регистрируем пользователя
    bot.db.register_user(user.id, user.username, user.first_name)

    # Получаем баланс
    stats = bot.db.get_user_stats(user.id)
    balance = stats[1] if stats else 0

    # Простое приветствие
    await update.message.reply_text(
        f"🎲 Привет, {user.first_name}!\n"
        f"💰 Баланс: ${balance:.0f}\n\n"
        "Используйте /menu для открытия меню"
    )


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