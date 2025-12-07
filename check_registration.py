import sys

sys.path.insert(0, '.')

print("🔍 Проверяем регистрацию обработчиков дуэлей...")

try:
    from app.bot import DiceGameBot
    from app.handlers.duel_handlers import register_duel_handlers

    # Создаем бота
    bot = DiceGameBot()

    # Проверяем что duel_manager создан
    print(f"✅ DuelManager создан: {hasattr(bot, 'duel_manager')}")

    # Проверяем bot_data
    print(f"✅ bot_instance в bot_data: {'bot_instance' in bot.application.bot_data}")

    # Проверяем обработчики
    print(f"\n📋 Всего обработчиков: {len(bot.application.handlers)}")

    # Ищем обработчики дуэлей
    duel_handlers = []
    for handler in bot.application.handlers:
        handler_str = str(handler)
        if 'duel' in handler_str.lower():
            duel_handlers.append(handler)

    print(f"🎯 Обработчиков дуэлей найдено: {len(duel_handlers)}")

    if duel_handlers:
        print("\n📝 Список обработчиков дуэлей:")
        for i, handler in enumerate(duel_handlers, 1):
            print(f"  {i}. {type(handler).__name__}")
            if hasattr(handler, 'pattern'):
                print(f"     Pattern: {handler.pattern}")

    # Проверяем callback handlers
    print("\n🔍 Ищем CallbackQueryHandler:")
    callback_count = 0
    for handler in bot.application.handlers:
        if 'CallbackQueryHandler' in str(type(handler)):
            callback_count += 1
            print(f"  CallbackQueryHandler {callback_count}: {handler}")
            if hasattr(handler, 'pattern'):
                print(f"    Pattern: {handler.pattern}")

    print(f"\n✅ Все проверки завершены")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback

    traceback.print_exc()