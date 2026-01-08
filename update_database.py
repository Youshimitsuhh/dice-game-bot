# update_database.py
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_database():
    """Обновление структуры базы данных"""
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect('dice_game.db')
        cursor = conn.cursor()

        logger.info("🔄 Обновление структуры базы данных...")

        # 1. Добавляем поле crypto_pay_id в таблицу users
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN crypto_pay_id TEXT")
            logger.info("✅ Добавлено поле crypto_pay_id в таблицу users")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logger.info("✅ Поле crypto_pay_id уже существует")
            else:
                logger.error(f"❌ Ошибка добавления поля crypto_pay_id: {e}")

        # 2. Создаем таблицу payments (если не существует)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                status TEXT DEFAULT 'pending',
                payment_type TEXT NOT NULL,
                crypto_pay_id TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                description TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        # 3. Создаем индексы для быстрого поиска
        indexes = [
            ('idx_payments_user_id', 'payments(user_id)'),
            ('idx_payments_status', 'payments(status)'),
            ('idx_payments_crypto_pay_id', 'payments(crypto_pay_id)')
        ]

        for index_name, index_sql in indexes:
            try:
                cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {index_sql}")
                logger.info(f"✅ Создан индекс {index_name}")
            except sqlite3.Error as e:
                logger.error(f"❌ Ошибка создания индекса {index_name}: {e}")

        # 4. Проверяем другие необходимые поля
        try:
            # Проверяем поле balance в users
            cursor.execute("SELECT balance FROM users LIMIT 1")
            logger.info("✅ Поле balance существует в таблице users")
        except sqlite3.OperationalError:
            logger.warning("⚠️ Поле balance отсутствует в таблице users")
            # Можно добавить если нужно
            # cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0.0")

        conn.commit()
        conn.close()

        logger.info("✅ База данных успешно обновлена!")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка обновления базы данных: {e}")
        raise


if __name__ == "__main__":
    update_database()