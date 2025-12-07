# debug_registration.py
import sys

sys.path.insert(0, '.')

print("🔍 Отладочная проверка регистрации...")

try:
    from telegram.ext import ApplicationBuilder
    from app.handlers.duel_handlers import register_duel_handlers
    from app.handlers.game_handlers import register_game_handlers
    from app.handlers.lobby_handlers import register_lobby_handlers
    from app.handlers.commands import register_command_handlers
    from app.handlers.buttons import register_button_handlers
    from app.handlers.messages import register_message_handlers

    # Создаем тестовое приложение
    application = ApplicationBuilder().token("test").build()


    # Мок-бот
    class MockBot:
        def __init__(self):
            self.db = None
            self.duel_manager = None
            self.game_manager = None
            self.lobby_manager = None


    bot = MockBot()

    print(f"📊 Начальное состояние: {len(application.handlers)} обработчиков")

    # Регистрируем по очереди и смотрим
    functions = [
        ("Дуэли", register_duel_handlers),
        ("Игры", register_game_handlers),
        ("Лобби", register_lobby_handlers),
        ("Команды", register_command_handlers),
        ("Кнопки", register_button_handlers),
        ("Сообщения", register_message_handlers),
    ]

    for name, func in functions:
        before = len(application.handlers)
        func(application, bot)
        after = len(application.handlers)
        added = after - before
        print(f"{name}: было {before}, стало {after} (+{added})")

    print(f"\n📊 Итог: {len(application.handlers)} обработчиков")

    if len(application.handlers) > 0:
        print("\n📝 Список обработчиков:")
        for i, handler in enumerate(application.handlers):
            print(f"  {i + 1}. {type(handler).__name__}")
    else:
        print("\n❌ НИ ОДНОГО обработчика не зарегистрировано!")

except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback

    traceback.print_exc()