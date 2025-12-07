# check_handlers_simple.py
import os

print("🔍 Проверяем все файлы handlers...")

handler_files = [
    'app/handlers/commands.py',
    'app/handlers/buttons.py',
    'app/handlers/messages.py',
    'app/handlers/lobby_handlers.py',
    'app/handlers/game_handlers.py',
    'app/handlers/duel_handlers.py',
]

for file_path in handler_files:
    print(f"\n=== {os.path.basename(file_path)} ===")

    if not os.path.exists(file_path):
        print("❌ Файл не найден")
        continue

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

        # Проверяем есть ли функция register_
        if 'def register_' in content:
            print("✅ Найдена register_ функция")

            # Проверяем есть ли add_handler
            if 'application.add_handler' in content:
                print("✅ Есть application.add_handler")
            else:
                print("❌ НЕТ application.add_handler!")
        else:
            print("❌ НЕТ register_ функции!")