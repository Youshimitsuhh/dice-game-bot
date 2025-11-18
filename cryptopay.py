# cryptopay.py
import requests
import json


class CryptoPay:
    def __init__(self, api_token):
        self.api_token = api_token
        self.base_url = "https://pay.crypt.bot/api/"

    def get_me(self):
        """Проверка подключения к API"""
        response = requests.get(
            f"{self.base_url}getMe",
            headers={"Crypto-Pay-API-Token": self.api_token}
        )
        return response.json()

    def create_invoice(self, amount, asset="USDT", description="Пополнение баланса"):
        """Создание счета для оплаты"""
        response = requests.post(
            f"{self.base_url}createInvoice",
            headers={"Crypto-Pay-API-Token": self.api_token},
            json={
                "asset": asset,
                "amount": str(amount),
                "description": description,
                "accepted_assets": ["USDT", "TON", "BTC"]
            }
        )
        return response.json()

    def get_invoices(self, invoice_ids=None, status=None):
        """Получение информации о счетах"""
        params = {}
        if invoice_ids:
            params["invoice_ids"] = invoice_ids
        if status:
            params["status"] = status

        response = requests.get(
            f"{self.base_url}getInvoices",
            headers={"Crypto-Pay-API-Token": self.api_token},
            params=params
        )
        return response.json()

    def transfer(self, user_id, amount, asset="USDT", spend_id=None):
        """Перевод средств пользователю"""
        response = requests.post(
            f"{self.base_url}transfer",
            headers={"Crypto-Pay-API-Token": self.api_token},
            json={
                "user_id": user_id,
                "asset": asset,
                "amount": str(amount),
                "spend_id": spend_id or f"transfer_{user_id}_{amount}"
            }
        )
        return response.json()

    def get_balance(self):
        """Получение баланса мерчанта"""
        response = requests.get(
            f"{self.base_url}getBalance",
            headers={"Crypto-Pay-API-Token": self.api_token}
        )
        return response.json()


# Тестирование перевода
if __name__ == "__main__":
    crypto = CryptoPay("488459:AAFiUz3cjBsDcYOlhAn3F988Rdqf1IWfjqP")
    print("🔗 Testing Crypto Pay API...")

    # Проверка баланса
    balance = crypto.get_balance()
    print("💰 Balance:", balance)

    # Создание тестового счета
    invoice = crypto.create_invoice(1.0, "USDT", "Тест игры в кости")
    print("📄 Invoice:", invoice)