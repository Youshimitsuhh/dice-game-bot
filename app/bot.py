# app/bot.py (обновляем)
import logging
from telegram.ext import ApplicationBuilder

from database import Database
from config import Config
from cryptopay import CryptoPay

# Импортируем наши обработчики
from app.handlers.commands import register_command_handlers
from app.handlers.buttons import register_button_handlers
from app.handlers.messages import register_message_handlers
from app.handlers.lobby_handlers import register_lobby_handlers  # <-- ДОБАВИЛИ

# Импортируем сервисы
from app.services.lobby_manager import LobbyManager


class DiceGameBot:
    def __init__(self):
        self.db = Database()
        self.config = Config()
        self.crypto_pay = CryptoPay(self.config.CRYPTO_PAY_TOKEN)

        # Менеджеры
        self.lobby_manager = LobbyManager(self.db)

        self.application = ApplicationBuilder().token(self.config.BOT_TOKEN).build()

        # Временные хранилища
        self.lobbies = {}  # TODO: Удалить после переноса всей логики
        self.games = {}
        self.duels = {}
        self.active_duels = {}

        # Регистрируем обработчики
        self.register_handlers()

        print("🤖 Бот инициализирован")

    def register_handlers(self):
        """Регистрация всех обработчиков"""
        logger = logging.getLogger(__name__)
        logger.info("📋 Регистрируем обработчики...")

        # 1. Регистрируем команды
        register_command_handlers(self.application, self)

        # 2. Регистрируем обработку кнопок
        register_button_handlers(self.application, self)

        # 3. Регистрируем обработку сообщений
        register_message_handlers(self.application, self)

        # 4. Регистрируем обработчики лобби
        register_lobby_handlers(self.application, self)  # <-- ДОБАВИЛИ

        logger.info("✅ Обработчики зарегистрированы")

    def run(self):
        """Запуск бота"""
        logging.info("🤖 Bot is starting...")
        self.application.run_polling()