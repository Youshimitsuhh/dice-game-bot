# test_duel_flow.py - ОБНОВЛЕННАЯ ВЕРСИЯ
import sys

sys.path.insert(0, '.')

from app.models.duel import Duel
from app.services.duel_manager import DuelManager
from database import Database

print("🔍 Тестируем полный цикл дуэли...")

try:
    # 1. Создаем БД и менеджер
    db = Database()
    manager = DuelManager(db)

    # 2. РЕГИСТРИРУЕМ ПОЛЬЗОВАТЕЛЕЙ (добавь это!)
    db.register_user(111, "player1", "Player One")
    db.register_user(222, "player2", "Player Two")

    # 3. Устанавливаем баланс (добавь в database.py метод или используй update_balance)
    # Для теста можно прямо в БД:
    import sqlite3

    conn = sqlite3.connect('dice_game.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = 1000 WHERE tg_id = 111")
    cursor.execute("UPDATE users SET balance = 1000 WHERE tg_id = 222")
    conn.commit()
    conn.close()

    print("✅ Пользователи зарегистрированы и баланс установлен")

    # 4. Создаем дуэль
    duel, error = manager.create_duel(
        chat_id=-1001234567890,
        creator_id=111,
        creator_name="Player1",
        bet_amount=10.0
    )

    if error:
        print(f"❌ Ошибка создания: {error}")
    else:
        print(f"✅ Дуэль создана: {duel.duel_id}")

        # 5. Принимаем дуэль
        duel, error = manager.accept_duel(
            duel_id=duel.duel_id,
            opponent_id=222,
            opponent_name="Player2"
        )

        if error:
            print(f"❌ Ошибка принятия: {error}")
        else:
            print(f"✅ Дуэль принята: {duel.creator_name} vs {duel.opponent_name}")

            # 6. Симулируем броски
            dice_values = [4, 5, 6]
            for i, value in enumerate(dice_values, 1):
                duel, error = manager.process_duel_roll(duel.duel_id, 111, value)
                if error:
                    print(f"❌ Бросок {i}: {error}")
                else:
                    print(f"✅ Игрок 1 бросок {i}: {value}, сумма: {duel.creator_total}")

            for i, value in enumerate([3, 2, 5], 1):
                duel, error = manager.process_duel_roll(duel.duel_id, 222, value)
                if error:
                    print(f"❌ Бросок {i}: {error}")
                else:
                    print(f"✅ Игрок 2 бросок {i}: {value}, сумма: {duel.opponent_total}")

            # 7. Результат
            print(f"\n🎲 Итог: {duel.creator_name}: {duel.creator_total} vs {duel.opponent_name}: {duel.opponent_total}")
            print(f"🏆 Победитель ID: {duel.winner_id}")
            print(f"📊 Статус: {duel.status}")

except Exception as e:
    print(f"❌ Общая ошибка: {e}")
    import traceback

    traceback.print_exc()