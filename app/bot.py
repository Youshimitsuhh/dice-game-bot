# app/bot.py (очищенный)
import logging
from telegram.ext import ApplicationBuilder

from database import Database
from config import Config
from cryptopay import CryptoPay

# Импортируем все обработчики из пакета
from app.handlers import (
    register_command_handlers,
    register_button_handlers,
    register_message_handlers,
    register_lobby_handlers
)

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

        # Регистрируем обработчики
        self.register_handlers()

        print("🤖 Бот инициализирован")

    def register_handlers(self):
        """Регистрация всех обработчиков"""
        logger = logging.getLogger(__name__)
        logger.info("📋 Регистрируем обработчики...")

        # ВАЖНО: Сначала специфичные обработчики
        register_lobby_handlers(self.application, self)

        # Потом общие обработчики
        register_command_handlers(self.application, self)
        register_button_handlers(self.application, self)
        register_message_handlers(self.application, self)

        logger.info("✅ Обработчики зарегистрированы")

    def run(self):
        """Запуск бота"""
        logging.info("🤖 Bot is starting...")
        self.application.run_polling()