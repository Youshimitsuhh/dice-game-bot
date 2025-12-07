# test_duels.py
import sys

sys.path.insert(0, '.')

print("🔍 Тестируем дуэли...")

try:
    # 1. Проверяем модель
    from app.models.duel import Duel

    print("✅ Модель Duel импортирована")

    # 2. Проверяем менеджер
    from app.services.duel_manager import DuelManager

    print("✅ DuelManager импортирован")

    # 3. Проверяем handlers
    from app.handlers.duel_handlers import register_duel_handlers

    print("✅ register_duel_handlers импортирован")

    # 4. Тестируем создание дуэли
    test_duel = Duel(
        duel_id="TEST1234",
        chat_id=-1001234567890,
        creator_id=123,
        creator_name="Test Creator",
        bet_amount=50.0
    )
    print(f"✅ Тестовая дуэль создана: {test_duel.duel_id}")

    # 5. Проверяем методы
    test_duel.add_roll(123, 5)
    print(f"✅ Бросок добавлен: {test_duel.creator_rolls}")

    print("\n🎉 ВСЕ ИМПОРТЫ ДУЭЛЕЙ РАБОТАЮТ!")
    print("Можно тестировать /duel команду!")

except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback

    traceback.print_exc()