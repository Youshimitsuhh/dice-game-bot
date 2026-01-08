# app/bot.py (очищенный)
import logging
from telegram.ext import ApplicationBuilder

from database import Database
from config import Config
# Убираем старый импорт cryptopay
# from cryptopay import CryptoPay

# Импортируем все обработчики из пакета
from app.handlers import (
    register_command_handlers,
    register_button_handlers,
    register_message_handlers,
    register_lobby_handlers,
    register_game_handlers,
    register_duel_handlers,
    register_payment_handlers  # ← НОВЫЙ ИМПОРТ
)

# Импортируем сервисы
from app.services.lobby_manager import LobbyManager
from app.services.game_manager import GameManager
from app.services.duel_manager import DuelManager
from app.services.payment_manager import PaymentManager  # ← НОВЫЙ ИМПОРТ


class DiceGameBot:
    def __init__(self):
        # Инициализация базы данных и конфига
        self.db = Database()
        self.config = Config()

        # Создаем соединение для платежного менеджера
        db_connection = self.db.get_connection()

        # Инициализация менеджеров
        self.payment_manager = PaymentManager(
            database=self.db,
            crypto_pay_token=self.config.CRYPTO_PAY_TOKEN
        )

        self.lobby_manager = LobbyManager(self.db)
        self.game_manager = GameManager(self.db, self.payment_manager)  # ← передаем payment_manager
        self.duel_manager = DuelManager(self.db, self.payment_manager)  # ← передаем payment_manager


        self.db_connection = db_connection

        # Создаем приложение
        self.application = ApplicationBuilder().token(self.config.BOT_TOKEN).build()

        # Регистрируем обработчики
        self.register_handlers()

        print("🤖 Бот инициализирован с платежной системой!")

    def __del__(self):
        """Закрытие соединения при уничтожении объекта"""
        if hasattr(self, 'db_connection'):
            self.db_connection.close()

    def register_handlers(self):
        """Регистрация всех обработчиков в ПРАВИЛЬНОМ ПОРЯДКЕ"""
        logger = logging.getLogger(__name__)
        logger.info("📋 Регистрируем обработчики...")

        # Сохраняем ссылку на экземпляр бота
        self.application.bot_data['bot_instance'] = self

        # ВАЖНО: Порядок регистрации КРИТИЧЕСКИ ВАЖЕН!
        # Сначала самые специфичные обработчики, потом общие

        # 1. Самые специфичные - дуэли (с фильтрацией по паттерну)
        logger.info("🔄 1/7: Регистрация обработчиков ДУЭЛЕЙ...")
        register_duel_handlers(self.application, self)

        # 2. Обработчики игр
        logger.info("🔄 2/7: Регистрация обработчиков ИГР...")
        register_game_handlers(self.application, self)

        # 3. Обработчики лобби
        logger.info("🔄 3/7: Регистрация обработчиков ЛОББИ...")
        register_lobby_handlers(self.application, self)

        # 4. Обработчики ПЛАТЕЖЕЙ (должны быть перед общими кнопками)
        logger.info("🔄 4/7: Регистрация обработчиков ПЛАТЕЖЕЙ...")
        register_payment_handlers(self.application, self)

        # 5. Команды (/start, /menu и т.д.)
        logger.info("🔄 5/7: Регистрация обработчиков КОМАНД...")
        register_command_handlers(self.application, self)

        # 6. ОБЩИЕ кнопки (должен быть ПОСЛЕ всех специфичных!)
        logger.info("🔄 6/7: Регистрация ОБЩЕГО обработчика кнопок...")
        register_button_handlers(self.application, self)

        # 7. Обработчики текстовых сообщений (самые общие)
        logger.info("🔄 7/7: Регистрация обработчиков СООБЩЕНИЙ...")
        register_message_handlers(self.application, self)

        # Отладочная информация
        self._log_handler_registration()

    def _log_handler_registration(self):
        """Логирует информацию о зарегистрированных обработчиках"""
        logger = logging.getLogger(__name__)
        logger.info("✅ Все обработчики зарегистрированы")

        # Простая проверка - выведем количество
        try:
            if hasattr(self.application, 'handlers') and isinstance(self.application.handlers, list):
                logger.info(f"📊 Обработчиков в списке: {len(self.application.handlers)}")

                # Выводим типы первых обработчиков
                for i in range(min(5, len(self.application.handlers))):
                    try:
                        handler = self.application.handlers[i]
                        handler_type = type(handler).__name__
                        logger.info(f"  {i + 1}. Тип: {handler_type}")
                    except:
                        pass
        except Exception as e:
            logger.error(f"❌ Ошибка при логировании обработчиков: {e}")

    def run(self):
        """Запуск бота"""
        logging.info("🤖 Bot is starting with payment system...")
        self.application.run_polling()