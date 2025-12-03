# test_imports.py
print("🔍 Проверка импортов...")

try:
    from database import Database

    print("✅ database.py импортирован")

    from config import Config

    print("✅ config.py импортирован")

    from cryptopay import CryptoPay

    print("✅ cryptopay.py импортирован")

    from app.bot import DiceGameBot

    print("✅ app.bot импортирован")

    from app.handlers.commands import register_command_handlers

    print("✅ handlers.commands импортированы")

    from app.services.lobby_manager import LobbyManager

    print("✅ services.lobby_manager импортирован")

    print("\n🎉 Все импорты работают!")

except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    import traceback

    traceback.print_exc()