# test_duel_registration.py
import sys

sys.path.insert(0, '.')

print("🔍 Тестируем регистрацию дуэлей...")

try:
    from telegram.ext import ApplicationBuilder
    from app.handlers.duel_handlers import register_duel_handlers
    from database import Database


    # Создаем мок-бот
    class MockBot:
        def __init__(self):
            self.db = Database()


    # Создаем приложение
    application = ApplicationBuilder().token("test_token").build()
    bot = MockBot()

    print(f"📊 До регистрации обработчиков: {len(application.handlers)}")

    # Регистрируем
    register_duel_handlers(application, bot)

    print(f"📊 После регистрации дуэлей: {len(application.handlers)}")

    if len(application.handlers) > 0:
        print("\n✅ Обработчики зарегистрированы!")
        for i, handler in enumerate(application.handlers):
            print(f"  {i + 1}. {type(handler).__name__}")
            if hasattr(handler, 'pattern'):
                print(f"     Pattern: {handler.pattern}")
    else:
        print("\n❌ Нет обработчиков!")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback

    traceback.print_exc()