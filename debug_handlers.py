# debug_handlers.py
import sys

sys.path.insert(0, '.')

from app.bot import DiceGameBot

bot = DiceGameBot()

print("🔍 Проверяем обработчики...")
print(f"Всего обработчиков: {len(bot.application.handlers)}")

for i, handler in enumerate(bot.application.handlers, 1):
    print(f"\n{i}. {type(handler).__name__}")

    # Для CallbackQueryHandler
    if hasattr(handler, 'pattern'):
        print(f"   Pattern: {handler.pattern}")

    # Для CommandHandler
    if hasattr(handler, 'commands'):
        print(f"   Commands: {handler.commands}")