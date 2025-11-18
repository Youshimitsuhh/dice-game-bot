from config import Config
import sqlite3
import logging
import json

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path='dice_game.db'):
        self.db_path = db_path
        self.config = Config()
        self.init_db()
        self.add_crypto_pay_column()
        self.update_games_table()
        self.add_game_code_column()

    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def add_game_code_column(self):
        """Добавляем поле game_code если его нет"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('ALTER TABLE games ADD COLUMN game_code TEXT UNIQUE')
            print("✅ Column game_code added successfully")
        except sqlite3.OperationalError:
            print("✅ Column game_code already exists")

        conn.commit()
        conn.close()

    def update_games_table(self):
        """Добавляем поля для 3 бросков если их нет"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Добавляем каждое поле если его нет
        try:
            cursor.execute('ALTER TABLE games ADD COLUMN player1_rolls TEXT DEFAULT "[]"')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE games ADD COLUMN player2_rolls TEXT DEFAULT "[]"')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE games ADD COLUMN player1_rolls_count INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute('ALTER TABLE games ADD COLUMN player2_rolls_count INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        conn.commit()
        conn.close()


    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    balance REAL DEFAULT 0.0,
                    crypto_pay_id INTEGER,
                    games_played INTEGER DEFAULT 0,
                    games_won INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица игр
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player1_id INTEGER NOT NULL,
                    player2_id INTEGER,
                    bet_amount REAL NOT NULL,
                    player1_score INTEGER,
                    player2_score INTEGER,
                    winner_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    game_code TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    finished_at DATETIME,
                    player1_rolls TEXT DEFAULT '[]',
                    player2_rolls TEXT DEFAULT '[]',  
                    player1_rolls_count INTEGER DEFAULT 0,
                    player2_rolls_count INTEGER DEFAULT 0,
                    FOREIGN KEY (player1_id) REFERENCES users (id)
                )
            ''')

            # Таблица транзакций
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS crypto_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    invoice_id INTEGER,
                    amount REAL NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    status TEXT DEFAULT 'completed',
                    crypto_asset TEXT DEFAULT 'USDT',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

            conn.commit()
            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            conn.rollback()
        finally:
            conn.close()


    def register_user(self, telegram_id, username, first_name):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, username, first_name) 
            VALUES (?, ?, ?)
        ''', (telegram_id, username, first_name))
        conn.commit()
        conn.close()

    def save_dice_roll(self, game_id, telegram_id, roll_value):
        """Сохраняет бросок игрока и возвращает обновленные данные"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Определяем какой игрок бросает
        cursor.execute('''
            SELECT player1_id, player2_id FROM games g
            JOIN users u1 ON g.player1_id = u1.id
            WHERE g.id = ? AND (u1.telegram_id = ? OR (SELECT u2.telegram_id FROM users u2 WHERE g.player2_id = u2.id) = ?)
        ''', (game_id, telegram_id, telegram_id))
        game = cursor.fetchone()

        if not game:
            conn.close()
            return None

        player1_id, player2_id = game
        is_player1 = telegram_id == self.get_user_telegram_id(player1_id)

        # Получаем текущие броски
        if is_player1:
            cursor.execute('SELECT player1_rolls, player1_rolls_count FROM games WHERE id = ?', (game_id,))
        else:
            cursor.execute('SELECT player2_rolls, player2_rolls_count FROM games WHERE id = ?', (game_id,))

        result = cursor.fetchone()
        current_rolls = json.loads(result[0]) if result[0] else []
        rolls_count = result[1]

        # Добавляем новый бросок
        current_rolls.append(roll_value)
        rolls_count += 1

        # Сохраняем обновленные данные
        if is_player1:
            cursor.execute('UPDATE games SET player1_rolls = ?, player1_rolls_count = ? WHERE id = ?',
                           (json.dumps(current_rolls), rolls_count, game_id))
        else:
            cursor.execute('UPDATE games SET player2_rolls = ?, player2_rolls_count = ? WHERE id = ?',
                           (json.dumps(current_rolls), rolls_count, game_id))

        conn.commit()

        # Получаем обновленные данные игры
        cursor.execute(
            'SELECT player1_rolls, player2_rolls, player1_rolls_count, player2_rolls_count FROM games WHERE id = ?',
            (game_id,))
        game_data = cursor.fetchone()
        conn.close()

        return {
            'current_rolls': current_rolls,
            'rolls_count': rolls_count,
            'total_rolls': sum(current_rolls),
            'is_player1': is_player1,
            'player1_rolls': json.loads(game_data[0]) if game_data[0] else [],
            'player2_rolls': json.loads(game_data[1]) if game_data[1] else [],
            'player1_rolls_count': game_data[2],
            'player2_rolls_count': game_data[3]
        }

    def check_both_players_finished(self, game_id):
        """Проверяет, оба ли игрока сделали по 3 броска"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT player1_rolls_count, player2_rolls_count FROM games WHERE id = ?', (game_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] >= 3 and result[1] >= 3

    def calculate_final_scores(self, game_id):
        """Вычисляет финальные суммы бросков"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT player1_rolls, player2_rolls FROM games WHERE id = ?', (game_id,))
        result = cursor.fetchone()
        conn.close()

        player1_rolls = json.loads(result[0]) if result[0] else []
        player2_rolls = json.loads(result[1]) if result[1] else []

        player1_total = sum(player1_rolls)
        player2_total = sum(player2_rolls)

        # Сохраняем финальные суммы
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE games SET player1_score = ?, player2_score = ? WHERE id = ?',
                       (player1_total, player2_total, game_id))
        conn.commit()
        conn.close()

        return player1_total, player2_total

    def get_user(self, telegram_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
        user = cursor.fetchone()
        conn.close()
        return user

    def update_balance(self, telegram_id, amount):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET balance = balance + ? WHERE telegram_id = ?
        ''', (amount, telegram_id))
        conn.commit()
        conn.close()

    def add_crypto_pay_column(self):
        """Добавляем поле crypto_pay_id если его нет"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('ALTER TABLE users ADD COLUMN crypto_pay_id INTEGER')
            print("✅ Column crypto_pay_id added successfully")
        except sqlite3.OperationalError:
            print("✅ Column crypto_pay_id already exists")

        conn.commit()
        conn.close()

    def get_game(self, game_code):
        """Находит игру только по коду"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT g.*, u1.telegram_id as p1_tg_id, u2.telegram_id as p2_tg_id,
                   u1.username as p1_username, u2.username as p2_username
            FROM games g 
            LEFT JOIN users u1 ON g.player1_id = u1.id 
            LEFT JOIN users u2 ON g.player2_id = u2.id 
            WHERE g.game_code = ?
        ''', (game_code,))

        game = cursor.fetchone()

        # ОТЛАДКА СТРУКТУРЫ
        if game:
            print(f"🔍 DATABASE: get_game структура ({len(game)} элементов):")
            print(f"   [0] id: {game[0]}")
            print(f"   [1] player1_id: {game[1]}")
            print(f"   [2] player2_id: {game[2]}")
            print(f"   [3] bet_amount: {game[3]}")
            print(f"   [15] p1_tg_id: {game[15]}")
            print(f"   [16] p2_tg_id: {game[16]}")
            print(f"   [17] p1_username: {game[17]}")
            print(f"   [18] p2_username: {game[18]}")

        conn.close()
        return game

    def join_game(self, game_code, user_id):
        print(f"🔍 DATABASE: join_game вызван с кодом '{game_code}' для пользователя {user_id}")

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Ищем игру по коду
            cursor.execute('''
                SELECT g.*, u1.telegram_id as p1_tg_id
                FROM games g 
                JOIN users u1 ON g.player1_id = u1.id 
                WHERE g.game_code = ? AND g.status = 'waiting'
            ''', (game_code,))

            game = cursor.fetchone()
            print(f"🔍 DATABASE: Найдена игра: {game}")

            if not game:
                print("❌ DATABASE: Игра не найдена или статус не 'waiting'")
                return False, "Игра не найдена или уже началась"

            # ПРАВИЛЬНЫЙ ИНДЕКС - p1_tg_id теперь на 16 позиции
            p1_tg_id = game[15]
            if p1_tg_id == user_id:
                print("❌ DATABASE: Пользователь пытается присоединиться к своей игре")
                return False, "Нельзя присоединиться к своей игре"

            # Получаем username пользователя
            cursor.execute('SELECT username FROM users WHERE telegram_id = ?', (user_id,))
            user_data = cursor.fetchone()
            p2_username = user_data[0] if user_data else "Игрок"

            # Проверяем баланс пользователя
            cursor.execute('SELECT balance FROM users WHERE telegram_id = ?', (user_id,))
            user_balance = cursor.fetchone()[0]
            bet_amount = game[3]  # bet_amount на 3 позиции

            print(f"🔍 DATABASE: Баланс пользователя: {user_balance}, Ставка: {bet_amount}")

            if user_balance < bet_amount:
                print("❌ DATABASE: Недостаточно средств")
                return False, f"Недостаточно средств. Нужно: ${bet_amount}"

            # Получаем ID пользователя для вставки в player2_id
            cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (user_id,))
            user_db_id = cursor.fetchone()[0]

            # Обновляем игру - добавляем второго игрока
            cursor.execute('''
                UPDATE games 
                SET player2_id = ?, status = 'active'
                WHERE game_code = ?
            ''', (user_db_id, game_code))

            # Резервируем средства второго игрока
            cursor.execute('''
                UPDATE users SET balance = balance - ? WHERE telegram_id = ?
            ''', (bet_amount, user_id))

            conn.commit()
            print("✅ DATABASE: Игрок успешно присоединился к игре")
            return True, "Успешное присоединение"

        except Exception as e:
            print(f"❌ DATABASE: Ошибка в join_game: {e}")
            conn.rollback()
            return False, f"Ошибка: {str(e)}"
        finally:
            conn.close()

    def debug_fix_join(self, game_code, user_id):
        """Временный фикс для join"""
        print(f"🔧 DEBUG_FIX: join {game_code} для {user_id}")

        conn = self.get_connection()
        cursor = conn.cursor()

        # Просто создаем тестовую игру если нет
        cursor.execute('''
            INSERT OR IGNORE INTO games 
            (player1_id, bet_amount, status, game_code) 
            VALUES (1, 10, 'waiting', ?)
        ''', (game_code,))

        conn.commit()
        conn.close()

        return True, "Фикс сработал"

    def create_game(self, telegram_id, bet_amount):
        conn = self.get_connection()
        cursor = conn.cursor()

        # Генерируем уникальный код
        game_code = self.generate_game_code()

        print(f"🔍 DATABASE: Создаем игру с кодом {game_code} для пользователя {telegram_id}")

        cursor.execute('''
            INSERT INTO games (player1_id, bet_amount, status, game_code) 
            VALUES ((SELECT id FROM users WHERE telegram_id = ?), ?, 'waiting', ?)
        ''', (telegram_id, bet_amount, game_code))

        game_id = cursor.lastrowid
        conn.commit()
        conn.close()

        print(f"✅ DATABASE: Игра создана! ID: {game_id}, Код: {game_code}, Статус: waiting")
        return game_id, game_code


    def get_game_by_id(self, game_id):
        """Находит игру по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT g.*, u1.telegram_id as p1_tg_id, u2.telegram_id as p2_tg_id,
                   u1.username as p1_username, u2.username as p2_username
            FROM games g 
            LEFT JOIN users u1 ON g.player1_id = u1.id 
            LEFT JOIN users u2 ON g.player2_id = u2.id 
            WHERE g.id = ?
        ''', (game_id,))

        game = cursor.fetchone()
        conn.close()
        return game

    def get_game_by_id(self, game_id):
        """Находит игру по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT g.*, u1.telegram_id as p1_tg_id, u2.telegram_id as p2_tg_id,
                   u1.username as p1_username, u2.username as p2_username
            FROM games g 
            LEFT JOIN users u1 ON g.player1_id = u1.id 
            LEFT JOIN users u2 ON g.player2_id = u2.id 
            WHERE g.id = ?
        ''', (game_id,))

        game = cursor.fetchone()
        conn.close()
        return game

    def save_dice_roll(self, game_id, telegram_id, roll_value):
        """Сохраняет бросок игрока и возвращает обновленные данные"""
        print(f"🔍 DATABASE: save_dice_roll для game_id {game_id}, user {telegram_id}, value {roll_value}")

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Определяем какой игрок бросает
            cursor.execute('''
                SELECT player1_id, player2_id FROM games g
                JOIN users u1 ON g.player1_id = u1.id
                WHERE g.id = ? AND (u1.telegram_id = ? OR g.player2_id IS NOT NULL AND 
                      (SELECT u2.telegram_id FROM users u2 WHERE g.player2_id = u2.id) = ?)
            ''', (game_id, telegram_id, telegram_id))
            game = cursor.fetchone()

            if not game:
                print("❌ DATABASE: Игра не найдена или игрок не участвует")
                return None

            player1_id, player2_id = game
            is_player1 = telegram_id == self.get_user_telegram_id(player1_id)

            # Получаем текущие броски
            if is_player1:
                cursor.execute('SELECT player1_rolls, player1_rolls_count FROM games WHERE id = ?', (game_id,))
            else:
                cursor.execute('SELECT player2_rolls, player2_rolls_count FROM games WHERE id = ?', (game_id,))

            result = cursor.fetchone()
            current_rolls = json.loads(result[0]) if result[0] else []
            rolls_count = result[1]

            # Добавляем новый бросок
            current_rolls.append(roll_value)
            rolls_count += 1

            # Сохраняем обновленные данные
            if is_player1:
                cursor.execute('UPDATE games SET player1_rolls = ?, player1_rolls_count = ? WHERE id = ?',
                               (json.dumps(current_rolls), rolls_count, game_id))
            else:
                cursor.execute('UPDATE games SET player2_rolls = ?, player2_rolls_count = ? WHERE id = ?',
                               (json.dumps(current_rolls), rolls_count, game_id))

            conn.commit()

            # Получаем обновленные данные игры
            cursor.execute(
                'SELECT player1_rolls, player2_rolls, player1_rolls_count, player2_rolls_count FROM games WHERE id = ?',
                (game_id,))
            game_data = cursor.fetchone()

            result_data = {
                'current_rolls': current_rolls,
                'rolls_count': rolls_count,
                'total_so_far': sum(current_rolls),
                'is_player1': is_player1,
                'player1_rolls': json.loads(game_data[0]) if game_data[0] else [],
                'player2_rolls': json.loads(game_data[1]) if game_data[1] else [],
                'player1_rolls_count': game_data[2],
                'player2_rolls_count': game_data[3]
            }

            print(f"✅ DATABASE: Бросок сохранен: {result_data}")
            return result_data

        except Exception as e:
            print(f"❌ DATABASE: Ошибка в save_dice_roll: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()

    def get_user_telegram_id(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def check_both_players_rolled(self, game_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT player1_score, player2_score FROM games WHERE id = ?', (game_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] is not None and result[1] is not None

    def get_user_stats(self, telegram_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT username, balance, games_played, games_won,
                   CASE WHEN games_played > 0 THEN ROUND(games_won * 100.0 / games_played, 1) ELSE 0 END as win_rate
            FROM users WHERE telegram_id = ?
        ''', (telegram_id,))
        stats = cursor.fetchone()
        conn.close()
        return stats

    def generate_game_code(self):
        """Генерирует уникальный короткий код для игры"""
        import random
        import string

        while True:
            # Генерируем код из 6 символов (буквы и цифры)
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

            # Проверяем уникальность
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM games WHERE game_code = ?', (code,))
            exists = cursor.fetchone()
            conn.close()

            if not exists:
                return code

    def finish_game(self, game_id, crypto_pay):
        """Завершаем игру и создаем чек победителю"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Получаем данные игры
        cursor.execute('''
            SELECT g.bet_amount, g.player1_rolls, g.player2_rolls,
                   u1.telegram_id as p1_id, u2.telegram_id as p2_id,
                   u1.username as p1_username, u2.username as p2_username
            FROM games g
            JOIN users u1 ON g.player1_id = u1.id
            JOIN users u2 ON g.player2_id = u2.id
            WHERE g.id = ?
        ''', (game_id,))
        game = cursor.fetchone()

        bet_amount, player1_rolls, player2_rolls, p1_id, p2_id, p1_username, p2_username = game

        # Вычисляем суммы 3 бросков
        player1_total = sum(json.loads(player1_rolls)) if player1_rolls else 0
        player2_total = sum(json.loads(player2_rolls)) if player2_rolls else 0

        total_bank = bet_amount * 2  # Общий банк
        commission = total_bank * self.config.COMMISSION_RATE
        winner_prize = total_bank - commission  # Чистый выигрыш

        winner_id = None
        winner_username = None

        # Определяем победителя
        if player1_total > player2_total:
            winner_id = p1_id
            winner_username = p1_username
        elif player2_total > player1_total:
            winner_id = p2_id
            winner_username = p2_username

        check_result = None

        if winner_id:
            try:
                # СОЗДАЕМ ЧЕК ДЛЯ ПОБЕДИТЕЛЯ
                check_result = crypto_pay.create_invoice(
                    amount=winner_prize,
                    asset="USDT",
                    description=f"🎉 Выигрыш в игре #{game_id}",
                    hidden_message=f"Поздравляем с победой! Ваш выигрыш: ${winner_prize:.2f}"
                )

                if check_result.get('ok'):
                    # Обновляем статистику
                    cursor.execute('UPDATE users SET games_won = games_won + 1 WHERE telegram_id = ?', (winner_id,))
                    cursor.execute(
                        'UPDATE games SET winner_id = (SELECT id FROM users WHERE telegram_id = ?), status = "finished" WHERE id = ?',
                        (winner_id, game_id))

                    # Сохраняем транзакцию
                    cursor.execute('''
                        INSERT INTO crypto_transactions (user_id, amount, type, status, crypto_asset, description)
                        VALUES (?, ?, 'game_win', 'completed', 'USDT', ?)
                    ''', (winner_id, winner_prize, f"Выигрыш в игре #{game_id}"))

                else:
                    # Если чек не создался - возвращаем средства игрокам
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p1_id))
                    cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p2_id))
                    cursor.execute('UPDATE games SET status = "failed" WHERE id = ?', (game_id,))

            except Exception as e:
                # В случае ошибки - возвращаем средства
                cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p1_id))
                cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p2_id))
                cursor.execute('UPDATE games SET status = "failed" WHERE id = ?', (game_id,))
                check_result = {'error': str(e)}
        else:
            # Ничья - возвращаем средства
            cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p1_id))
            cursor.execute('UPDATE users SET balance = balance + ? WHERE telegram_id = ?', (bet_amount, p2_id))
            cursor.execute('UPDATE games SET status = "finished" WHERE id = ?', (game_id,))

        # Обновляем статистику игр
        cursor.execute('UPDATE users SET games_played = games_played + 1 WHERE telegram_id IN (?, ?)', (p1_id, p2_id))

        conn.commit()
        conn.close()

        return {
            'player1_total': player1_total,
            'player2_total': player2_total,
            'winner_id': winner_id,
            'winner_username': winner_username,
            'winner_prize': winner_prize,
            'commission': commission,
            'check_result': check_result,
            'success': bool(winner_id and check_result and check_result.get('ok'))
        }