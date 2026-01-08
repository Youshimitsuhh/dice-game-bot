import sqlite3

conn = sqlite3.connect('dice_game.db')
cursor = conn.cursor()

# Проверьте таблицу users
cursor.execute("PRAGMA table_info(users)")
print("📊 Структура таблицы users:")
for column in cursor.fetchall():
    print(f"  {column[1]} ({column[2]})")

# Проверьте несколько пользователей
cursor.execute("SELECT * FROM users LIMIT 3")
print("\n👥 Первые 3 пользователя:")
for row in cursor.fetchall():
    print(f"  {row}")

conn.close()