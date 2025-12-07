import sys
sys.path.insert(0, '.')

print("🔍 Проверяем импорты напрямую...")

modules_to_check = [
    ("app.handlers.commands", "register_command_handlers"),
    ("app.handlers.buttons", "register_button_handlers"),
    ("app.handlers.messages", "register_message_handlers"),
    ("app.handlers.lobby_handlers", "register_lobby_handlers"),
    ("app.handlers.game_handlers", "register_game_handlers"),
    ("app.handlers.duel_handlers", "register_duel_handlers"),
]

for module_path, func_name in modules_to_check:
    try:
        module = __import__(module_path, fromlist=[func_name])
        func = getattr(module, func_name)
        print(f"✅ {module_path}.{func_name} - найдено")
    except ImportError as e:
        print(f"❌ {module_path} - ошибка импорта: {e}")
    except AttributeError as e:
        print(f"❌ {module_path}.{func_name} - функция не найдена: {e}")
    except Exception as e:
        print(f"❌ {module_path} - другая ошибка: {e}")
