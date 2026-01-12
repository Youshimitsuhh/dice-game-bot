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
        self.game_manager = GameManager(self.db, self.payment_manager)
        self.duel_manager = DuelManager(self.db, self.payment_manager)

        self.games = {}
        self.active_lobby_games = {}

        self.db_connection = db_connection

        # Создаем приложение
        self.application = ApplicationBuilder().token(self.config.BOT_TOKEN).build()

        self.setup_cleanup_jobs()

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

        # 1. Команда /duel (должна быть отдельно, так как это команда)
        logger.info("🔄 1/8: Регистрация команды /duel...")
        from app.handlers.duel_handlers import duel_command
        from telegram.ext import CommandHandler
        self.application.add_handler(CommandHandler("duel", duel_command))

        # 2. Самые специфичные - дуэли (callback с фильтрацией по паттерну)
        logger.info("🔄 2/8: Регистрация обработчиков ДУЭЛЕЙ (callback)...")
        register_duel_handlers(self.application, self)

        # 3. Обработчики игр
        logger.info("🔄 3/8: Регистрация обработчиков ИГР...")
        register_game_handlers(self.application, self)

        # 4. Обработчики лобби
        logger.info("🔄 4/8: Регистрация обработчиков ЛОББИ...")
        register_lobby_handlers(self.application, self)

        # 5. Команды (/start, /menu и т.д.)
        logger.info("🔄 5/8: Регистрация обработчиков КОМАНД...")
        register_command_handlers(self.application, self)

        # 6. ОБЩИЕ кнопки (должен быть ПОСЛЕ всех специфичных!)
        logger.info("🔄 6/8: Регистрация ОБЩЕГО обработчика кнопок...")
        register_button_handlers(self.application, self)

        # 7. Обработчики ПЛАТЕЖЕЙ (теперь после общих кнопок)
        logger.info("🔄 7/8: Регистрация обработчиков ПЛАТЕЖЕЙ...")
        # Проверяем, существует ли этот модуль
        try:
            register_payment_handlers(self.application, self)
            logger.info("✅ Обработчики платежей зарегистрированы")
        except Exception as e:
            logger.warning(f"⚠️ Обработчики платежей не зарегистрированы: {e}")

        # 8. Обработчики текстовых сообщений (самые общие)
        logger.info("🔄 8/8: Регистрация обработчиков СООБЩЕНИЙ...")
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

    def setup_cleanup_jobs(self):
        """Настраивает фоновые задачи очистки"""
        import logging
        logger = logging.getLogger(__name__)

        if hasattr(self.application, 'job_queue') and self.application.job_queue:
            # Очистка старых лобби каждые 60 секунд
            self.application.job_queue.run_repeating(
                self.cleanup_old_lobbies_job,
                interval=60.0,  # Каждую минуту
                first=30.0  # Запустить через 30 секунд после старта
            )
            logger.info("✅ Фоновая очистка лобби настроена (каждые 60 сек)")
        else:
            logger.warning("⚠️ Job queue недоступен, фоновая очистка отключена")

    async def cleanup_old_lobbies_job(self, context):
        """Фоновая задача для очистки старых лобби"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            removed_count = self.lobby_manager.cleanup_old_lobbies(timeout_minutes=5)
            if removed_count > 0:
                logger.info(f"🧹 Удалено {removed_count} старых лобби")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки лобби: {e}")

    def run(self):
        """Запуск бота"""
        logging.info("🤖 Bot is starting with payment system...")
        self.application.run_polling()