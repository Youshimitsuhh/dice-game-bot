import httpx
import logging
import asyncio
from typing import Optional, Dict, Any, List
from uuid import uuid4
import json
import time

logger = logging.getLogger(__name__)

TEST_MODE = True

class CryptoPayService:
    """Сервис для работы с Crypto Pay API"""

    def __init__(self, api_token: str):
        """Сервис для работы с Crypto Pay API"""
        self.api_token = api_token
        self.base_url = "https://pay.crypt.bot/api"
        self.client = None
        self.test_mode = TEST_MODE
        self._init_client()

        # Обновляем логирование
        mode_text = "ТЕСТОВЫЙ" if self.test_mode else "РЕАЛЬНЫЙ"
        logger.info(f"✅ CryptoPayService инициализирован (режим: {mode_text})")

    def _init_client(self):
        """Инициализация HTTP клиента"""
        self.client = httpx.AsyncClient(
            headers={
                "Crypto-Pay-API-Token": self.api_token,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Универсальный метод для запросов к API"""
        try:
            url = f"{self.base_url}/{endpoint}"

            if method.upper() == "GET":
                response = await self.client.get(url, params=kwargs.get('params'))
            else:
                response = await self.client.post(url, json=kwargs.get('json'))

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    return data.get("result")
                else:
                    logger.error(f"❌ API Error: {data.get('error', {})}")
            else:
                logger.error(f"❌ HTTP {response.status_code}: {response.text}")

            return None

        except httpx.TimeoutException:
            logger.error("❌ Timeout при запросе к Crypto Pay API")
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка Crypto Pay API: {e}")
            return None

    async def create_invoice(
            self,
            amount: float,
            asset: str = "USDT",
            description: str = "Пополнение баланса",
            payload: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Создание чека для оплаты"""
        if self.test_mode:
            logger.info(f"🔧 ТЕСТОВЫЙ РЕЖИМ: Создание инвойса на ${amount}")

            return {
                "invoice_id": f"test_invoice_{int(time.time())}",
                "pay_url": f"https://t.me/CryptoBot?start=test_invoice_{int(time.time())}",
                "status": "active",
                "payload": payload or f"test_{uuid4().hex[:8]}",
                "asset": asset,
                "amount": amount
            }

        if payload is None:
            payload = str(uuid4())

        invoice = await self._make_request(
            "POST",
            "createInvoice",
            json={
                "asset": asset,
                "amount": str(amount),
                "description": description,
                "hidden_message": f"Оплата #{payload[:8]}",
                "paid_btn_name": "viewItem",
                "paid_btn_url": "https://t.me/batler_dice_bot",
                "payload": payload,
                "allow_comments": False,
                "allow_anonymous": False,
                "expires_in": 3600  # 1 час
            }
        )

        if invoice:
            return {
                "invoice_id": invoice.get("invoice_id"),
                "pay_url": invoice.get("pay_url"),
                "status": invoice.get("status"),
                "payload": payload,
                "asset": asset,
                "amount": amount
            }
        return None

    async def create_check(
            self,
            amount: float,
            asset: str = "USDT",
            description: str = "Пополнение баланса",
            payload: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Создание чека для оплаты внутри Telegram
        Документация: https://help.crypt.bot/payments-api#createCheck
        """
        if self.test_mode:
            logger.info(f"🔧 ТЕСТОВЫЙ РЕЖИМ: Создание чека на ${amount}")

            return {
                "invoice_id": f"test_check_{int(time.time())}",
                "pay_url": f"https://t.me/CryptoBot?start=test_check_{int(time.time())}",
                "status": "active",
                "payload": payload or f"test_{uuid4().hex[:8]}",
                "asset": asset,
                "amount": amount
            }

        if payload is None:
            payload = str(uuid4())

        # Формируем имя для чека (макс 128 символов)
        check_name = description[:100] if len(description) > 100 else description

        check = await self._make_request(
            "POST",
            "createCheck",  # ← КЛЮЧЕВОЕ ОТЛИЧИЕ: createCheck вместо createInvoice
            json={
                "asset": asset,
                "amount": str(amount),
                "name": check_name,
                "payload": payload,
                "allow_comments": False,
                "allow_anonymous": False
                # Для чеков нет expires_in, по умолчанию 24 часа
            }
        )

        if check:
            # Возвращаем ту же структуру для совместимости
            return {
                "invoice_id": check.get("check_id"),  # check_id вместо invoice_id
                "pay_url": check.get("bot_invoice_url"),  # deep link для оплаты в Telegram
                "status": check.get("status"),
                "payload": payload,
                "asset": asset,
                "amount": amount
            }
        return None

    async def transfer(
            self,
            user_id: int,
            amount: float,
            asset: str = "USDT",
            spend_id: Optional[str] = None,
            comment: str = "Вывод средств"
    ) -> Optional[Dict[str, Any]]:
        """Вывод средств пользователю"""
        if self.test_mode:
            logger.info(f"🔧 ТЕСТОВЫЙ РЕЖИМ: Вывод ${amount} пользователю {user_id}")

            return {
                "transfer_id": f"test_transfer_{int(time.time())}",
                "status": "completed",  # В тестовом режиме сразу completed
                "hash": f"test_hash_{uuid4().hex[:16]}",
                "spend_id": spend_id or f"test_{uuid4().hex[:8]}"
            }

        if spend_id is None:
            spend_id = str(uuid4())[:32]

        transfer = await self._make_request(
            "POST",
            "transfer",
            json={
                "user_id": user_id,
                "asset": asset,
                "amount": str(amount),
                "spend_id": spend_id,
                "comment": comment
            }
        )

        if transfer:
            return {
                "transfer_id": transfer.get("id"),
                "status": transfer.get("status"),
                "hash": transfer.get("hash"),
                "spend_id": spend_id
            }
        return None

    async def get_invoices(
            self,
            invoice_ids: Optional[List[str]] = None,
            status: Optional[str] = None,
            offset: int = 0,
            count: int = 100
    ) -> Optional[List[Dict[str, Any]]]:
        """Получение списка инвойсов"""
        params = {"offset": offset, "count": count}

        if invoice_ids:
            params["invoice_ids"] = ",".join(invoice_ids)
        if status:
            params["status"] = status

        result = await self._make_request("GET", "getInvoices", params=params)
        return result.get("items") if result else None

    async def get_transfers(
            self,
            transfer_ids: Optional[List[str]] = None,
            status: Optional[str] = None,
            offset: int = 0,
            count: int = 100
    ) -> Optional[List[Dict[str, Any]]]:
        """Получение списка переводов"""
        params = {"offset": offset, "count": count}

        if transfer_ids:
            params["transfer_ids"] = ",".join(transfer_ids)
        if status:
            params["status"] = status

        result = await self._make_request("GET", "getTransfers", params=params)
        return result.get("items") if result else None

    async def get_balance(self) -> Optional[List[Dict[str, Any]]]:
        """Получение баланса бота"""
        return await self._make_request("GET", "getBalance")

    async def get_exchange_rates(self) -> Optional[List[Dict[str, Any]]]:
        """Получение курсов обмена"""
        return await self._make_request("GET", "getExchangeRates")

    async def get_currencies(self) -> Optional[List[Dict[str, Any]]]:
        """Получение списка поддерживаемых валют"""
        return await self._make_request("GET", "getCurrencies")

    async def check_invoice_status(self, invoice_id: str) -> Optional[str]:
        """Проверка статуса конкретного инвойса"""
        invoices = await self.get_invoices(invoice_ids=[invoice_id])
        if invoices and len(invoices) > 0:
            return invoices[0].get("status")
        return None

    async def is_invoice_paid(self, invoice_id: str) -> bool:
        """Проверка, оплачен ли инвойс"""
        status = await self.check_invoice_status(invoice_id)
        return status == "paid"

    async def create_test_invoice(self, amount: float = 1.0) -> Optional[Dict[str, Any]]:
        """Создание тестового инвойса (для отладки)"""
        return await self.create_invoice(
            amount=amount,
            asset="USDT",
            description="Тестовый платеж",
            payload=f"test_{uuid4().hex[:8]}"
        )

    async def close(self):
        """Закрытие клиента"""
        if self.client:
            await self.client.aclose()
            logger.info("✅ CryptoPayService клиент закрыт")

    async def __aenter__(self):
        """Контекстный менеджер"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер - выход"""
        await self.close()


# Утилитарные функции для конвертации валют
class CurrencyConverter:
    """Конвертер валют (упрощенный)"""

    @staticmethod
    async def usd_to_crypto(amount_usd: float, asset: str = "USDT") -> float:
        """
        Конвертация USD в криптовалюту
        В реальном приложении нужно использовать актуальные курсы
        """
        # Примерные курсы (должны получаться из API)
        rates = {
            "USDT": 1.0,  # 1 USDT ≈ 1 USD
            "TON": 4.5,  # 1 TON ≈ 4.5 USD
            "BTC": 50000.0,  # 1 BTC ≈ 50000 USD
            "ETH": 3000.0,  # 1 ETH ≈ 3000 USD
        }

        rate = rates.get(asset, 1.0)
        return amount_usd / rate

    @staticmethod
    async def crypto_to_usd(amount_crypto: float, asset: str = "USDT") -> float:
        """Конвертация криптовалюты в USD"""
        rates = {
            "USDT": 1.0,
            "TON": 4.5,
            "BTC": 50000.0,
            "ETH": 3000.0,
        }

        rate = rates.get(asset, 1.0)
        return amount_crypto * rate