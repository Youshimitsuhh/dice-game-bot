# check_return_values.py
import sys

sys.path.insert(0, '.')

print("🔍 Проверяем что возвращают функции register_...")

try:
    from telegram.ext import ApplicationBuilder

    # Тестовое приложение
    app = ApplicationBuilder().token("test").build()


    # Мок-бот
    class MockBot:
        pass


    bot = MockBot()

    # Проверяем каждую функцию
    modules = [
        ('duel_handlers', 'register_duel_handlers'),
        ('game_handlers', 'register_game_handlers'),
        ('lobby_handlers', 'register_lobby_handlers'),
        ('commands', 'register_command_handlers'),
        ('buttons', 'register_button_handlers'),
        ('messages', 'register_message_handlers'),
    ]

    for module_name, func_name in modules:
        module = __import__(f'app.handlers.{module_name}', fromlist=[func_name])
        func = getattr(module, func_name)

        print(f"\n=== {func_name} ===")

        # Вызываем и смотрим что возвращает
        try:
            result = func(app, bot)
            print(f"Результат: {result} (тип: {type(result)})")

            if result is not None:
                print(f"⚠️ Функция ВОЗВРАЩАЕТ значение вместо регистрации!")
        except Exception as e:
            print(f"❌ Ошибка при вызове: {e}")

except Exception as e:
    print(f"❌ Общая ошибка: {e}")
    import traceback

    traceback.print_exc()