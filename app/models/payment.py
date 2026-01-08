import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging
import uuid

logger = logging.getLogger(__name__)


@dataclass
class Payment:
    """Модель платежа"""
    payment_id: str
    user_id: int
    amount: float
    currency: str = "USD"
    status: str = "pending"  # pending, completed, failed, refunded, cancelled
    payment_type: str = "deposit"  # deposit, withdraw
    crypto_pay_id: Optional[str] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


class PaymentModel:
    """Работа с платежами в базе данных"""

    def __init__(self, db_connection: sqlite3.Connection):
        self.db = db_connection
        self._init_table()

    def _init_table(self):
        """Инициализация таблицы платежей"""
        cursor = self.db.cursor()
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

        # Индексы для быстрого поиска
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_payments_crypto_pay_id ON payments(crypto_pay_id)')

        self.db.commit()
        logger.info("✅ Таблица payments создана/проверена")

    def create_payment(self, payment: Payment) -> bool:
        """Создание нового платежа"""
        try:
            cursor = self.db.cursor()
            cursor.execute('''
                INSERT INTO payments 
                (payment_id, user_id, amount, currency, status, payment_type, 
                 crypto_pay_id, created_at, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                payment.payment_id,
                payment.user_id,
                payment.amount,
                payment.currency,
                payment.status,
                payment.payment_type,
                payment.crypto_pay_id,
                payment.created_at,
                payment.description
            ))
            self.db.commit()
            logger.info(f"✅ Платеж {payment.payment_id} создан для пользователя {payment.user_id}")
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка создания платежа: {e}")
            return False

    def get_payment(self, payment_id: str) -> Optional[Payment]:
        """Получение платежа по ID"""
        cursor = self.db.cursor()
        cursor.execute('''
            SELECT payment_id, user_id, amount, currency, status, 
                   payment_type, crypto_pay_id, created_at, completed_at, description
            FROM payments WHERE payment_id = ?
        ''', (payment_id,))

        row = cursor.fetchone()
        if row:
            return Payment(*row)
        return None

    def get_payment_by_crypto_id(self, crypto_pay_id: str) -> Optional[Payment]:
        """Получение платежа по crypto_pay_id"""
        cursor = self.db.cursor()
        cursor.execute('''
            SELECT payment_id, user_id, amount, currency, status, 
                   payment_type, crypto_pay_id, created_at, completed_at, description
            FROM payments WHERE crypto_pay_id = ?
        ''', (crypto_pay_id,))

        row = cursor.fetchone()
        if row:
            return Payment(*row)
        return None

    def update_payment_status(self, payment_id: str, status: str, crypto_pay_id: str = None) -> bool:
        """Обновление статуса платежа"""
        try:
            cursor = self.db.cursor()

            if crypto_pay_id:
                cursor.execute('''
                    UPDATE payments 
                    SET status = ?, crypto_pay_id = ?, completed_at = ?
                    WHERE payment_id = ?
                ''', (status, crypto_pay_id, datetime.now().isoformat(), payment_id))
            elif status in ["completed", "failed", "cancelled"]:
                cursor.execute('''
                    UPDATE payments 
                    SET status = ?, completed_at = ?
                    WHERE payment_id = ?
                ''', (status, datetime.now().isoformat(), payment_id))
            else:
                cursor.execute('''
                    UPDATE payments 
                    SET status = ?
                    WHERE payment_id = ?
                ''', (status, payment_id))

            self.db.commit()
            logger.info(f"✅ Платеж {payment_id} обновлен: статус={status}")
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка обновления платежа {payment_id}: {e}")
            return False

    def get_user_payments(self, user_id: int, limit: int = 10, payment_type: str = None) -> list:
        """Получение платежей пользователя"""
        cursor = self.db.cursor()

        if payment_type:
            cursor.execute('''
                SELECT payment_id, amount, currency, status, payment_type, created_at, description
                FROM payments 
                WHERE user_id = ? AND payment_type = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, payment_type, limit))
        else:
            cursor.execute('''
                SELECT payment_id, amount, currency, status, payment_type, created_at, description
                FROM payments 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit))

        return cursor.fetchall()

    def get_pending_payments(self, hours: int = 24) -> list:
        """Получение pending платежей за последние N часов"""
        cursor = self.db.cursor()
        time_threshold = datetime.now().isoformat()

        cursor.execute('''
            SELECT payment_id, user_id, amount, payment_type, created_at
            FROM payments 
            WHERE status = 'pending' 
            AND datetime(created_at) > datetime('now', ?)
        ''', (f'-{hours} hours',))

        return cursor.fetchall()