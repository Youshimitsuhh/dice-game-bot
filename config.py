import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    CRYPTO_PAY_TOKEN = "488629:AABjVxCcyvvBDE4rbeeoPJyGwSw3N1ZJN4Z"
    COMMISSION_RATE = 0.08
    MIN_BET = 1.0
    MIN_WITHDRAWAL = 1.0


