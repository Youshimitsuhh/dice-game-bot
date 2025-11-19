import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла (для локальной разработки)
load_dotenv()


class Config:
    # Telegram Bot Token (получаем из переменных окружения)
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8067592113:AAFdP5CNVzS7b1jy0j1X0v5YxUvvN7Dp2B8')

    # Crypto Pay API (получаем из переменных окружения)
    CRYPTO_PAY_TOKEN = os.getenv('CRYPTO_PAY_TOKEN', '488629:AABjVxCcyvvBDE4rbeeoPJyGwSw3N1ZJN4Z')

    # Game settings (оставляем как есть)
    COMMISSION_RATE = 0.08
    MIN_BET = 1.0
    MIN_WITHDRAWAL = 1.0

    # Webhook settings for Render
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
    WEBAPP_HOST = os.getenv('WEBAPP_HOST', '0.0.0.0')
    WEBAPP_PORT = int(os.getenv('PORT', 5000))


# Создаем экземпляр конфигурации
config = Config()

