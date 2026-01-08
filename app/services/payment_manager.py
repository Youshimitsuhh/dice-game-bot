import logging
import asyncio
from typing import Optional, Tuple, Dict, Any, List
from uuid import uuid4
from datetime import datetime, timedelta

from app.models.payment import Payment, PaymentModel
from app.services.crypto_pay_service import CryptoPayService, CurrencyConverter

logger = logging.getLogger(__name__)


class PaymentManager:
    """Менеджер платежей - основная бизнес-логика"""

    def __init__(self, database, crypto_pay_token: str):
        """
        Инициализация менеджера платежей

        Args:
            database: объект Database или соединение SQLite
            crypto_pay_token: токен Crypto Pay
        """
        # Сохраняем оригинальный объект
        self.database = database

        # Получаем соединение для работы с БД
        if hasattr(database, 'get_connection'):
            # Это объект Database
            self.connection = database.get_connection()
        else:
            # Это сырое соединение SQLite
            self.connection = database

        # Алиас для совместимости (если где-то используется self.db)
        self.db = self.connection

        # Инициализируем модель платежей
        self.payment_model = PaymentModel(self.connection)

        # Инициализируем сервисы
        self.crypto_pay = CryptoPayService(crypto_pay_token)
        self.converter = CurrencyConverter()

        logger.info("✅ PaymentManager инициализирован")

    def _get_connection(self):
        """Получение соединения с БД"""
        if self.database:
            return self.database.get_connection()
        else:
            # Возвращаем соединение из модели (осторожно с закрытием!)
            return self.payment_model.db

    def _execute_query(self, query, params=()):
        """Выполнение SQL запроса с автоматическим управлением соединением"""
        print(f"🔍 DEBUG: Выполняем запрос: {query}")
        print(f"🔍 DEBUG: Параметры: {params}")

        if self.database:
            conn = self.database.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            conn.commit()
            conn.close()
            return result
        else:
            # Для сырого соединения
            cursor = self.payment_model.db.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
            self.payment_model.db.commit()
            return result

    # ==================== ДЕПОЗИТЫ ====================

    async def create_deposit(
            self,
            user_id: int,
            amount_usd: float,
            asset: str = "USDT",
            description: str = None
    ) -> Tuple[Optional[Payment], Optional[str], Optional[str]]:
        """
        Создание депозита

        Args:
            user_id: ID пользователя
            amount_usd: сумма в USD
            asset: криптовалюта (USDT, TON, BTC, ETH)
            description: описание платежа

        Returns:
            (Payment, pay_url, error_message)
        """
        try:
            # Проверяем минимальную сумму
            if amount_usd < 1.0:
                return None, None, "Минимальная сумма депозита: $1"

            if amount_usd > 10000.0:
                return None, None, "Максимальная сумма депозита: $10,000"

            # Конвертируем USD в криптовалюту
            amount_crypto = await self.converter.usd_to_crypto(amount_usd, asset)

            # Создаем уникальный ID платежа
            payment_id = f"dep_{uuid4().hex[:12].upper()}"

            # Создаем платеж
            payment = Payment(
                payment_id=payment_id,
                user_id=user_id,
                amount=amount_usd,  # Сохраняем в USD для отображения
                currency="USD",
                payment_type="deposit",
                description=description or f"Пополнение на ${amount_usd:.2f}"
            )

            # Сохраняем в БД
            if not self.payment_model.create_payment(payment):
                return None, None, "Ошибка создания платежа в базе данных"

            # Создаем инвойс в Crypto Pay
            invoice = await self.crypto_pay.create_check(
                amount=amount_crypto,
                asset=asset,
                description=payment.description,
                payload=payment_id
            )

            if not invoice:
                # Отмечаем платеж как failed
                self.payment_model.update_payment_status(payment_id, "failed")
                return None, None, "Ошибка создания счета в платежной системе"

            # Обновляем платеж с crypto_pay_id
            self.payment_model.update_payment_status(
                payment_id=payment_id,
                status="pending",
                crypto_pay_id=invoice["invoice_id"]
            )

            logger.info(f"✅ Депозит создан: {payment_id} для пользователя {user_id}")
            return payment, invoice["pay_url"], None

        except Exception as e:
            logger.error(f"❌ Ошибка создания депозита: {e}", exc_info=True)
            return None, None, f"Внутренняя ошибка: {str(e)}"

    async def check_deposit_status(self, payment_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Проверка статуса депозита

        Returns:
            (status, error_message)
        """
        try:
            payment = self.payment_model.get_payment(payment_id)
            if not payment:
                return None, "Платеж не найден"

            if payment.status == "completed":
                return "completed", None

            if not payment.crypto_pay_id:
                return payment.status, None

            # Проверяем статус в Crypto Pay
            is_paid = await self.crypto_pay.is_invoice_paid(payment.crypto_pay_id)

            if is_paid:
                # Зачисляем средства
                cursor = self.connection.cursor()
                cursor.execute('''UPDATE users SET balance = balance + ? WHERE telegram_id = ?''', (payment.amount, payment.user_id))

                self.payment_model.update_payment_status(payment_id, "completed")
                self.database.commit()

                logger.info(f"✅ Депозит завершен: {payment_id}, зачислено ${payment.amount:.2f}")
                return "completed", None

            # Проверяем не истек ли срок
            created_at = datetime.fromisoformat(payment.created_at)
            if datetime.now() - created_at > timedelta(hours=1):
                self.payment_model.update_payment_status(payment_id, "expired")
                return "expired", None

            return payment.status, None

        except Exception as e:
            logger.error(f"❌ Ошибка проверки депозита {payment_id}: {e}")
            return None, str(e)

    # ==================== ВЫВОД СРЕДСТВ ====================

    async def create_withdrawal(
            self,
            user_id: int,
            amount_usd: float,
            asset: str = "USDT",
            description: str = None
    ) -> Tuple[Optional[Payment], Optional[str]]:
        """
        Создание запроса на вывод средств

        Returns:
            (Payment, error_message)
        """
        try:
            # Проверяем баланс пользователя
            cursor = self.connection.cursor()
            cursor.execute('''
                SELECT balance, crypto_pay_id FROM users 
                WHERE telegram_id = ?
            ''', (user_id,))

            user_data = cursor.fetchone()
            if not user_data:
                return None, "Пользователь не найден"

            current_balance, crypto_pay_id = user_data

            # Проверки
            if amount_usd < 1.0:
                return None, "Минимальная сумма вывода: $1"

            if amount_usd > 5000.0:
                return None, "Максимальная сумма вывода: $5,000"

            if amount_usd > current_balance:
                return None, f"Недостаточно средств. Доступно: ${current_balance:.2f}"

            if not crypto_pay_id:
                return None, "Для вывода средств необходимо привязать Crypto Pay аккаунт"

            # Проверяем комиссию (8%)
            commission = amount_usd * 0.08
            total_amount = amount_usd - commission

            if total_amount < 0.01:
                return None, "Сумма после комиссии слишком мала"

            # Создаем платеж
            payment_id = f"wd_{uuid4().hex[:12].upper()}"
            payment = Payment(
                payment_id=payment_id,
                user_id=user_id,
                amount=total_amount,  # Сумма после комиссии
                currency="USD",
                payment_type="withdraw",
                description=description or f"Вывод ${amount_usd:.2f} (комиссия: ${commission:.2f})"
            )

            # Сохраняем в БД
            if not self.payment_model.create_payment(payment):
                return None, "Ошибка создания платежа"

            # Резервируем средства
            cursor.execute('''
                UPDATE users 
                SET balance = balance - ?
                WHERE telegram_id = ?
            ''', (amount_usd, user_id))

            self.database.commit()

            logger.info(f"✅ Запрос на вывод создан: {payment_id} для пользователя {user_id}")
            return payment, None

        except Exception as e:
            logger.error(f"❌ Ошибка создания вывода: {e}", exc_info=True)
            return None, f"Внутренняя ошибка: {str(e)}"

    async def process_withdrawal(self, payment_id: str) -> Tuple[bool, Optional[str]]:
        """Обработка вывода средств (должен выполняться администратором)"""
        try:
            payment = self.payment_model.get_payment(payment_id)
            if not payment:
                return False, "Платеж не найден"

            if payment.status != "pending":
                return False, f"Платеж уже обработан: {payment.status}"

            # Получаем crypto_pay_id пользователя
            cursor = self.connection.cursor()
            cursor.execute(
                'SELECT crypto_pay_id FROM users WHERE telegram_id = ?',  # ← ИСПРАВЛЕНО
                (payment.user_id,)
            )
            user_data = cursor.fetchone()

            if not user_data or not user_data[0]:
                # Возвращаем средства
                cursor.execute('''
                    UPDATE users 
                    SET balance = balance + ?
                    WHERE telegram_id = ?  # ← ИСПРАВЛЕНО
                ''', (payment.amount, payment.user_id))

                self.payment_model.update_payment_status(payment_id, "failed")
                self.database.commit()
                return False, "У пользователя не привязан Crypto Pay"

            crypto_pay_user_id = int(user_data[0])

            # Конвертируем USD в криптовалюту (по умолчанию USDT)
            amount_crypto = await self.converter.usd_to_crypto(payment.amount, "USDT")

            # Выполняем перевод
            transfer = await self.crypto_pay.transfer(
                user_id=crypto_pay_user_id,
                amount=amount_crypto,
                asset="USDT",
                comment=f"Вывод средств #{payment_id}"
            )

            if not transfer:
                # Возвращаем средства при ошибке
                cursor.execute('''
                    UPDATE users 
                    SET balance = balance + ?
                    WHERE telegram_id = ?  # ← ИСПРАВЛЕНО
                ''', (payment.amount, payment.user_id))

                self.payment_model.update_payment_status(payment_id, "failed")
                self.database.commit()
                return False, "Ошибка перевода в платежной системе"

            # Обновляем статус платежа
            self.payment_model.update_payment_status(payment_id, "completed")

            logger.info(f"✅ Вывод обработан: {payment_id}, отправлено ${payment.amount:.2f}")
            return True, None

        except Exception as e:
            logger.error(f"❌ Ошибка обработки вывода {payment_id}: {e}", exc_info=True)
            return False, str(e)

    async def cancel_withdrawal(self, payment_id: str, user_id: int = None) -> Tuple[bool, Optional[str]]:
        """Отмена запроса на вывод"""
        try:
            payment = self.payment_model.get_payment(payment_id)
            if not payment:
                return False, "Платеж не найден"

            if payment.status != "pending":
                return False, f"Невозможно отменить: статус {payment.status}"

            if user_id and payment.user_id != user_id:
                return False, "Вы можете отменять только свои запросы"

            # Возвращаем средства
            cursor = self.connection.cursor()
            cursor.execute('''UPDATE users SET balance = balance + ? WHERE telegram_id = ?''', (payment.amount, payment.user_id))

            self.payment_model.update_payment_status(payment_id, "cancelled")
            self.database.commit()

            logger.info(f"✅ Вывод отменен: {payment_id}")
            return True, None

        except Exception as e:
            logger.error(f"❌ Ошибка отмены вывода {payment_id}: {e}")
            return False, str(e)

    # ==================== УТИЛИТЫ ====================

    def get_user_balance(self, user_id: int) -> float:
        """Получение баланса пользователя в USD"""
        try:
            results = self._execute_query(
                'SELECT balance FROM users WHERE telegram_id = ?',  # ← ИСПРАВЛЕНО: telegram_id
                (user_id,)
            )
            if results and results[0] and results[0][0] is not None:
                return float(results[0][0])
            return 0.0

        except Exception as e:
            logger.error(f"❌ Ошибка получения баланса: {e}")
            return 0.0

    async def get_bot_balance(self) -> Optional[Dict[str, Any]]:
        """Получение баланса бота в Crypto Pay"""
        return await self.crypto_pay.get_balance()

    def get_user_payments(self, user_id: int, limit: int = 10, payment_type: str = None) -> List:
        """Получение истории платежей пользователя"""
        return self.payment_model.get_user_payments(user_id, limit, payment_type)

    async def check_pending_payments(self):
        """Проверка pending платежей (для cron задачи)"""
        try:
            pending_payments = self.payment_model.get_pending_payments(hours=24)

            for payment_data in pending_payments:
                payment_id = payment_data[0]
                payment_type = payment_data[3]

                if payment_type == "deposit":
                    await self.check_deposit_status(payment_id)
                # Для выводов нужна ручная обработка

            logger.info(f"✅ Проверено {len(pending_payments)} pending платежей")

        except Exception as e:
            logger.error(f"❌ Ошибка проверки pending платежей: {e}")

    def link_crypto_pay_account(self, user_id: int, crypto_pay_id: str) -> bool:
        """Привязка Crypto Pay аккаунта пользователя"""
        try:
            self._execute_query(
                'UPDATE users SET crypto_pay_id = ? WHERE telegram_id = ?',
                (crypto_pay_id, user_id)
            )
            logger.info(f"✅ Crypto Pay аккаунт привязан: пользователь {user_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка привязки Crypto Pay: {e}")
            return False

    def get_payment_stats(self, user_id: int = None) -> Dict[str, Any]:
        """Статистика по платежам"""
        stats = {
            "total_deposits": 0,
            "total_withdrawals": 0,
            "pending_withdrawals": 0,
            "total_commission": 0,
            "total_payments": 0
        }

        try:
            if user_id:
                results = self._execute_query('''
                    SELECT 
                        SUM(CASE WHEN payment_type = 'deposit' AND status = 'completed' THEN amount ELSE 0 END),
                        SUM(CASE WHEN payment_type = 'withdraw' AND status = 'completed' THEN amount ELSE 0 END),
                        SUM(CASE WHEN payment_type = 'withdraw' AND status = 'pending' THEN amount ELSE 0 END),
                        COUNT(*) as total_payments
                    FROM payments 
                    WHERE user_id = ?
                ''', (user_id,))
            else:
                results = self._execute_query('''
                    SELECT 
                        SUM(CASE WHEN payment_type = 'deposit' AND status = 'completed' THEN amount ELSE 0 END),
                        SUM(CASE WHEN payment_type = 'withdraw' AND status = 'completed' THEN amount ELSE 0 END),
                        SUM(CASE WHEN payment_type = 'withdraw' AND status = 'pending' THEN amount ELSE 0 END),
                        COUNT(*) as total_payments
                    FROM payments
                ''')

            if results and results[0] and results[0][0] is not None:
                stats["total_deposits"] = float(results[0][0]) or 0
                stats["total_withdrawals"] = float(results[0][1]) or 0
                stats["pending_withdrawals"] = float(results[0][2]) or 0
                stats["total_payments"] = results[0][3] or 0
                stats["total_commission"] = stats["total_deposits"] - stats["total_withdrawals"]

            return stats

        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики: {e}")
            return stats

    async def close(self):
        """Закрытие ресурсов"""
        await self.crypto_pay.close()