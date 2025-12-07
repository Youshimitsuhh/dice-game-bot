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
    register_lobby_handlers,
    register_game_handlers,
    register_duel_handlers
)

# Импортируем сервисы
from app.services.lobby_manager import LobbyManager
from app.services.game_manager import GameManager
from app.services.duel_manager import DuelManager


class DiceGameBot:
    def __init__(self):
        self.db = Database()
        self.config = Config()
        self.crypto_pay = CryptoPay(self.config.CRYPTO_PAY_TOKEN)

        # Менеджеры
        self.lobby_manager = LobbyManager(self.db)
        self.game_manager = GameManager(self.db)
        self.duel_manager = DuelManager(self.db)

        self.application = ApplicationBuilder().token(self.config.BOT_TOKEN).build()

        # Регистрируем обработчики
        self.register_handlers()

        print("🤖 Бот инициализирован")

    def register_handlers(self):
        """Регистрация всех обработчиков"""
        logger = logging.getLogger(__name__)
        logger.info("📋 Регистрируем обработчики...")

        self.application.bot_data['bot_instance'] = self

        # Прямые вызовы (временно)
        from app.handlers.duel_handlers import register_duel_handlers
        from app.handlers.game_handlers import register_game_handlers
        from app.handlers.lobby_handlers import register_lobby_handlers
        from app.handlers.commands import register_command_handlers
        from app.handlers.buttons import register_button_handlers
        from app.handlers.messages import register_message_handlers

        register_duel_handlers(self.application, self)
        register_game_handlers(self.application, self)
        register_lobby_handlers(self.application, self)
        register_command_handlers(self.application, self)
        register_button_handlers(self.application, self)
        register_message_handlers(self.application, self)

        total = len(self.application.handlers)
        logger.info(f"📊 Всего обработчиков зарегистрировано: {total}")

        if total < 6:
            logger.error(f"⚠️ Проблема: только {total} обработчиков!")
            # Выведем какие есть
            for i, handler in enumerate(self.application.handlers):
                logger.info(f"  {i + 1}. {type(handler).__name__}")

    def run(self):
        """Запуск бота"""
        logging.info("🤖 Bot is starting...")
        self.application.run_polling()