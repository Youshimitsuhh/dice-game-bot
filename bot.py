from telegram.ext import ApplicationBuilder
from telegram import MenuButtonCommands, BotCommand
import asyncio
import logging
import time
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import random
from cryptopay import CryptoPay

from config import Config
from database import Database

from flask import Flask, request, jsonify
import logging
import os
from datetime import datetime

from telegram import Update
from telegram.ext import Application, ContextTypes
import asyncio

application = None
app = Flask(__name__)

# ==================== HEALTH CHECK ENDPOINTS ====================
@app.route('/')
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "Dice Game Bot",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        update = Update.de_json(json_data, application.bot)

        # Асинхронная обработка update
        async def process_update():
            await application.process_update(update)

        asyncio.create_task(process_update())
        return '', 200

    except Exception as e:
        print(f"Webhook error: {e}")
        return '', 200


@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        from telegram import Bot
        from config import Config
        import asyncio

        async def set_webhook_async():
            bot = Bot(token=Config.BOT_TOKEN)
            webhook_url = "https://dice-game-bot-7acf.onrender.com/webhook"
            result = await bot.set_webhook(webhook_url)
            return result, webhook_url

        result, webhook_url = asyncio.run(set_webhook_async())

        return jsonify({"status": "success", "webhook_set": result, "url": webhook_url})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500




logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)


class DiceGameBot:
    def __init__(self):
        self.db = Database()
        self.config = Config()
        self.crypto_pay = CryptoPay(self.config.CRYPTO_PAY_TOKEN)

        # Telegram Application (единственный экземпляр)
        self.application = ApplicationBuilder().token(self.config.BOT_TOKEN).build()

        # Инициализация хранилищ лобби и игр
        self.lobbies = {}  # lobby_id -> lobby_data (используем список игроков внутри)
        self.games = {}  # active games in memory: game_id -> game_state

        self.duels = {}  # chat_id: duel_data
        self.active_duels = {}  # {message_id: duel_data}

        # Регистрируем обработчики (в register_handlers используем self.application)
        self.register_handlers()

    def register_handlers(self):
        print("🔍 DEBUG: Регистрируем обработчики...")

        # Команды
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("create", self.create_lobby_command))
        self.application.add_handler(CommandHandler("duel", self.duel_command))
        self.application.add_handler(CommandHandler("join", self.join_command))
        self.application.add_handler(CommandHandler("deposit", self.deposit_command))
        self.application.add_handler(CommandHandler("join_lobby", self.join_lobby_command))

        # Отдельный обработчик для /help
        self.application.add_handler(CommandHandler("help", self.help_command))

        # Обработчики дуэлей
        self.application.add_handler(CallbackQueryHandler(self.duel_roll_handler, pattern=r"^duel_roll"))
        self.application.add_handler(CallbackQueryHandler(self.duel_buttons_handler, pattern=r"^duel_"))

        # Обработчики для лобби - ТОЛЬКО конкретные действия
        self.application.add_handler(CallbackQueryHandler(self._handle_create_lobby_cb, pattern=r"^create_lobby:"))
        self.application.add_handler(CallbackQueryHandler(self._handle_lobby_callbacks,
                                                          pattern=r"^lobby_toggle_ready:|^lobby_start:|^lobby_leave:"))  # ← ИЗМЕНИЛИ ПАТТЕРН
        self.application.add_handler(CallbackQueryHandler(self._handle_join_lobby_cb, pattern=r"^join_lobby:"))
        self.application.add_handler(CallbackQueryHandler(self._handle_copy_lobby_cb, pattern=r"^copy_lobby:"))

        # Общий обработчик для остальных inline-кнопок (он идёт последним)
        self.application.add_handler(CallbackQueryHandler(self.button_handler))

        # Тексты/сообщения
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        print("🔍 DEBUG: Обработчики зарегистрированы")


    async def ask_custom_bet(self, query):
        """Запрашиваем произвольную сумму ставки"""
        await query.edit_message_text(
            "💵 Введите сумму ставки (минимум $1):\n\n"
            "Пример: 15 или 75.5",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
            ])
        )


    async def copy_command(self, query, game_code):
        """Показывает команду для копирования"""
        await query.edit_message_text(
            f"📋 **Команда для присоединения:**\n\n"
            f"`/join {game_code}`\n\n"
            "Просто скопируй и отправь другу!",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
            ])
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat

        # Обработка глубоких ссылок для присоединения к лобби
        if context.args and context.args[0].startswith('joinlobby_'):
            lobby_id = context.args[0][10:]  # Убираем 'joinlobby_'
            await self.join_lobby_from_deeplink(update, context, lobby_id)
            return

        # Обработка глубоких ссылок для присоединения к игре 1 на 1
        if context.args and context.args[0].startswith('join_'):
            game_code = context.args[0][5:]  # Убираем 'join_' (5 символов)
            await self.join_from_deeplink(update, context, game_code)
            return

        # Старая обработка (для обратной совместимости)
        if context.args and context.args[0].startswith('join'):
            game_code = context.args[0][4:]  # Убираем 'join' (4 символа)
            await self.join_from_deeplink(update, context, game_code)
            return

        # Блокируем старт в групповых чатах
        if chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "🎯 Для игры в кости используйте команды:\n\n"
                "/duel <ставка> - создать дуэль\n"
                "/join <код> - присоединиться к игре\n\n"
                "📱 Для пополнения баланса и настроек перейдите в личный чат с ботом."
            )
            return

        user = update.effective_user
        self.db.register_user(user.id, user.username, user.first_name)

        # Получаем статистику для показа в меню
        stats = self.db.get_user_stats(user.id)
        balance = stats[1] if stats else 0

        welcome_text = (
            f"🎲 Привет, {user.first_name}!\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            "Выберите действие:"
        )

        keyboard = [
            [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
            [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(welcome_text, reply_markup=reply_markup)

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = query.from_user.id
        chat_id = query.message.chat.id

        print(f"🔍 DEBUG button_handler: START data='{data}', user_id={user_id}, chat_id={chat_id}")

        if data == "find_game":
            print("🔍 DEBUG: Обрабатываем find_game")
            await self.show_bet_options(query)
        elif data == "create_lobby_menu":
            print("🔍 DEBUG: Обрабатываем create_lobby_menu")
            await self.show_lobby_options(query)
        elif data.startswith("lobby_bet_"):
            bet_amount = float(data.split("_")[2])
            print(f"🔍 DEBUG: Обрабатываем lobby_bet_{bet_amount}")
            await self.show_lobby_size_options(query, bet_amount)
        elif data == "lobby_custom_bet":
            print("🔍 DEBUG: Обрабатываем lobby_custom_bet")
            context.user_data['waiting_for_lobby_bet'] = True
            await self.ask_custom_lobby_bet(query)
        elif data.startswith("lobby_size_"):
            parts = data.split("_")
            bet_amount = float(parts[2])
            max_players = int(parts[3])
            print(f"🔍 DEBUG: Обрабатываем lobby_size_{bet_amount}_{max_players}")
            await self.create_lobby_with_bet(query, bet_amount, max_players)
        elif data == "lobby_cancel":  # ← ИСПРАВЛЕНА СТРОКА (добавлена закрывающая скобка)
            print("🔍 DEBUG: Обрабатываем lobby_cancel")
            await self.show_main_menu(query)
        elif data == "stats":
            print("🔍 DEBUG: Обрабатываем stats")
            await self.show_stats(query)
        elif data == "main_menu":
            print("🔍 DEBUG: Обрабатываем main_menu")
            await self.show_main_menu(query)
        elif data.startswith("bet_"):
            bet_amount = float(data.split("_")[1])
            print(f"🔍 DEBUG: Обрабатываем bet_{bet_amount}")
            await self.create_game(query, bet_amount)
        elif data.startswith("roll_"):
            game_id = int(data.split("_")[1])
            print(f"🔍 DEBUG: Обрабатываем roll_{game_id}")
            await self.roll_dice(query, game_id, context)
        elif data == "help":
            print("🔍 DEBUG: Обрабатываем help")
            await self.show_help(query)
        elif data == "deposit":
            print("🔍 DEBUG: Обрабатываем deposit")
            await self.show_deposit(query)
        elif data.startswith("deposit_"):
            amount = float(data.split("_")[1])
            print(f"🔍 DEBUG: Обрабатываем deposit_{amount}")
            await self.process_deposit(query, amount)
        elif data == "custom_bet":
            print("🔍 DEBUG: Обрабатываем custom_bet")
            context.user_data['waiting_for_bet'] = True
            await self.ask_custom_bet(query)
        elif data == "withdraw":
            print("🔍 DEBUG: Обрабатываем withdraw")
            await self.show_withdraw(query)
        elif data.startswith("withdraw_"):
            amount = float(data.split("_")[1])
            print(f"🔍 DEBUG: Обрабатываем withdraw_{amount}")
            await self.process_withdraw(query, amount)
        elif data == "custom_withdraw":
            print("🔍 DEBUG: Обрабатываем custom_withdraw")
            context.user_data['waiting_for_withdraw'] = True
            await self.ask_custom_withdraw(query)
        elif data == "custom_deposit":
            print("🔍 DEBUG: Обрабатываем custom_deposit")
            context.user_data['waiting_for_deposit'] = True
            await self.ask_custom_deposit(query)
        elif data.startswith("copy_"):
            game_code = data.split("_")[1]
            print(f"🔍 DEBUG: Обрабатываем copy_{game_code}")
            await self.copy_command(query, game_code)
        elif data == "cancel_game_creation":
            print("🔍 DEBUG: Обрабатываем cancel_game_creation")
            await self.cancel_game_creation(query)
        elif data.startswith("cancel_active_game_"):
            game_id = data.split("_")[3]
            print(f"🔍 DEBUG: Обрабатываем cancel_active_game_{game_id}")
            await self.cancel_active_game(query, game_id)
        elif data.startswith("cancel_duel_"):
            chat_id = int(data.split("_")[2])
            print(f"🔍 DEBUG: Обрабатываем cancel_duel_{chat_id}")
            await self.cancel_duel_in_chat(query, chat_id)
        else:
            print(f"🔍 DEBUG button_handler: НЕИЗВЕСТНАЯ КНОПКА data='{data}'")
            await query.edit_message_text(f"❌ Неизвестная команда: {data}")

        print(f"🔍 DEBUG button_handler: FINISHED data='{data}'")

    async def show_help(self, query):
        help_text = (
            "❓ Помощь по игре\n\n"
            "🎯 Как играть:\n"
            "1. Нажмите 'Создать игру'\n"
            "2. Выберите сумму ставки\n"
            "3. Другой игрок присоединяется по ID\n"
            "4. Бросайте кости\n"
            "5. Победитель забирает банк за вычетом комиссии 8%\n\n"
            "💸 Команды:\n"
            "/menu - открыть меню\n"
            "/deposit [сумма] - пополнить баланс\n"
            "/join [ID] - присоединиться к игре"
        )

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(help_text, reply_markup=reply_markup)

    async def show_bet_options(self, query):
        keyboard = [
            [InlineKeyboardButton("$1", callback_data="bet_1")],
            [InlineKeyboardButton("$5", callback_data="bet_5")],
            [InlineKeyboardButton("$10", callback_data="bet_10")],
            [InlineKeyboardButton("$25", callback_data="bet_25")],
            [InlineKeyboardButton("$50", callback_data="bet_50")],
            [InlineKeyboardButton("$100", callback_data="bet_100")],
            [InlineKeyboardButton("💵 Произвольная ставка", callback_data="custom_bet")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_game_creation")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text("🎯 Выберите сумму ставки:", reply_markup=reply_markup)

    async def ask_custom_bet(self, query):
        """Запрашиваем произвольную сумму ставки"""
        await query.edit_message_text(
            "💵 Введите сумму ставки (минимум $1):\n\n"
            "Пример: 15 или 75.5",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
            ])
        )

        async def ask_custom_deposit(self, query):
            """Запрашиваем произвольную сумму для депозита"""
            await query.edit_message_text(
                "💵 Введите сумму для пополнения (минимум $1):\n\n"
                "Пример: 15.5 или 75",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
                ])
            )

    async def show_balance(self, query):
        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        if user:
            balance = user[4]
            await query.edit_message_text(f"💰 Ваш баланс: {balance}")

    async def show_stats(self, query):
        user_id = query.from_user.id
        stats = self.db.get_user_stats(user_id)

        if stats:
            username, balance, games_played, games_won, win_rate = stats
            player_name = f"@{username}" if username else "Игрок"

            stats_text = (
                f"📊 Статистика {player_name}:\n\n"
                f"💰 Баланс: ${balance:.0f}\n"
                f"🎮 Игр сыграно: {games_played}\n"
                f"🏆 Побед: {games_won}\n"
                f"📈 Процент побед: {win_rate}%\n\n"
                f"💸 Комиссия системы: 8%"
            )

            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(stats_text, reply_markup=reply_markup)

    async def show_main_menu(self, query):
        print(f"🔍 DEBUG show_main_menu: вызван для пользователя {query.from_user.id}")

        user = query.from_user
        stats = self.db.get_user_stats(user.id)
        balance = stats[1] if stats else 0

        print(f"🔍 DEBUG: Баланс пользователя: {balance}")

        menu_text = (
            f"🎲 Главное меню\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            "Выберите действие:"
        )

        keyboard = [
            [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
            [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        print(f"🔍 DEBUG: Клавиатура создана, кнопок: {len(keyboard)}")

        await query.edit_message_text(menu_text, reply_markup=reply_markup)
        print("🔍 DEBUG: Сообщение отправлено")


    async def process_withdraw_from_message(self, update, amount):
        """Обрабатываем вывод из текстового сообщения"""
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)

        if not user:
            await update.message.reply_text("❌ Пользователь не найден")
            return

        balance = user[4]

        if balance < amount:
            await update.message.reply_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${balance:.0f}\n"
                f"Запрошено: ${amount:.0f}"
            )
            return

        if amount < 1:
            await update.message.reply_text("❌ Минимальная сумма вывода $1")
            return

        try:
            # РЕАЛЬНЫЙ ВЫВОД
            transfer_result = self.crypto_pay.transfer(
                user_id=user_id,
                amount=amount,
                asset="USDT",
                spend_id=f"withdraw_{user_id}_{amount}"
            )

            if transfer_result.get('ok'):
                self.db.update_balance(user_id, -amount)

                # Сохраняем транзакцию
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO crypto_transactions (user_id, amount, type, status, crypto_asset)
                    VALUES (?, ?, 'withdraw', 'completed', 'USDT')
                ''', (user_id, amount))
                conn.commit()
                conn.close()

                await update.message.reply_text(
                    f"✅ Вывод ${amount:.0f} выполнен!\n\n"
                    f"💸 Сумма отправлена на ваш кошелек Crypto Pay\n"
                    f"💰 Новый баланс: ${balance - amount:.0f}"
                )
            else:
                error_msg = transfer_result.get('error', 'Неизвестная ошибка')
                await update.message.reply_text(f"❌ Ошибка вывода: {error_msg}")

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при выводе: {str(e)}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user_id = update.effective_user.id
        message_text = update.message.text

        # ГРУППЫ
        if chat.type in ["group", "supergroup"]:
            if not (context.user_data.get('waiting_for_bet') or
                    context.user_data.get('waiting_for_deposit') or
                    context.user_data.get('waiting_for_withdraw')):
                return

        # ПРИВАТНЫЙ ЧАТ
        print(f"🔍 DEBUG: handle_message текст: '{message_text}'")

        # 1. Ожидаем ввод ставки для обычной игры
        if context.user_data.get('waiting_for_bet'):
            context.user_data['waiting_for_bet'] = False
            try:
                bet_amount = float(message_text)
                if bet_amount < 1:
                    await update.message.reply_text("❌ Минимальная ставка $1")
                    return
                await self.create_game_from_message(update, bet_amount)
            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму (например: 25 или 50.5)")
            return  # <-- ВЕРНУЛИ return НА МЕСТО

        # 2. Ожидаем ввод ставки для лобби
        if context.user_data.get('waiting_for_lobby_bet'):
            context.user_data['waiting_for_lobby_bet'] = False
            try:
                bet_amount = float(message_text)
                if bet_amount < 1:
                    await update.message.reply_text("❌ Минимальная ставка $1")
                    return
                await self.show_lobby_size_options_from_message(update, bet_amount)
            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму (например: 25 или 50.5)")
            return  # <-- ВЕРНУЛИ return

        # 3. Ожидаем ввод депозита
        elif context.user_data.get('waiting_for_deposit'):
            context.user_data['waiting_for_deposit'] = False
            try:
                amount = float(message_text)
                if amount < 1:
                    await update.message.reply_text("❌ Минимальная сумма $1")
                    return
                await self.process_deposit_from_message(update, amount)
            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму")
            return

        # 4. Ожидаем ввод вывода
        elif context.user_data.get('waiting_for_withdraw'):
            context.user_data['waiting_for_withdraw'] = False
            try:
                amount = float(message_text)
                await self.process_withdraw_from_message(update, amount)
            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму")
            return

        # Если сообщение не число - показываем меню
        try:
            float(message_text)
            await update.message.reply_text(
                "💡 Вы ввели число, но не выбрали действие.\n\n"
                "Используйте меню."
            )
        except ValueError:
            await self.menu_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat

        if chat.type in ["group", "supergroup"]:
            help_text = (
                "🎯 **Команды для игры в группах:**\n\n"
                "/duel <ставка> - создать дуэль\n"
                "Пример: /duel 10\n\n"
                "/join <код> - присоединиться к игре\n\n"
                "📱 *Для пополнения баланса и полного меню перейдите в личный чат с ботом*"
            )
        else:
            help_text = (
                "❓ **Помощь по игре**\n\n"
                "🎯 Как играть:\n"
                "1. Нажмите 'Создать игру'\n"
                "2. Выберите сумму ставки\n"
                "3. Другой игрок присоединяется по ID\n"
                "4. Бросайте кости\n"
                "5. Победитель забирает банк за вычетом комиссии 8%\n\n"
                "💸 Команды:\n"
                "/menu - открыть меню\n"
                "/join [ID] - присоединиться к игре\n"
                "/duel [ставка] - создать дуэль (в группах)\n\n"
                "💳 *Пополнение баланса доступно только через меню*"
            )

        await update.message.reply_text(help_text, parse_mode='Markdown')


    async def create_game_from_message(self, update, bet_amount):
        """Создает игру с произвольной ставкой из текстового сообщения"""
        user_id = update.effective_user.id
        user = self.db.get_user(user_id)

        if not user:
            await update.message.reply_text("❌ Сначала используйте /start")
            return

        current_balance = user[4]

        if current_balance < bet_amount:
            await update.message.reply_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${current_balance:.0f}\n"
                f"Требуется: ${bet_amount:.0f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                    [InlineKeyboardButton("🎯 Найти игру", callback_data="find_game")]
                ])
            )
            return

        # Создаем игру
        game_id, game_code = self.db.create_game(user_id, bet_amount)

        # Резервируем средства
        self.db.update_balance(user_id, -bet_amount)

        # Сообщение для создателя игры
        await update.message.reply_text(
            f"🎲 Игра создана!\n"
            f"💰 Ставка: ${bet_amount:.0f}\n\n"
            f"🆔 Код игры: `{game_code}`\n\n"
            "📤 **Просто перешли сообщение ниже другу!**",
            parse_mode='Markdown'
        )

        # Отдельное сообщение для пересылки с кнопкой
        await update.message.reply_text(
            f"🎯 Присоединяйся к игре в кости!\n\n"
            f"💰 Ставка: ${bet_amount:.0f}\n"
            f"🆔 Код: {game_code}\n\n"
            "Нажми кнопку ниже чтобы присоединиться:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ К ИГРЕ",
                                      url=f"https://t.me/Zarikionl_bot?start=join{game_code}")],
                [InlineKeyboardButton("📋 Или используй команду",
                                      callback_data="show_command")]
            ])
        )

    async def join_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        print(f"🔍 DEBUG: join_command вызван")
        print(f"🔍 DEBUG: context.args = {context.args}")

        try:
            game_code = context.args[0].upper()
            print(f"🔍 DEBUG: Код игры: '{game_code}'")

            user_id = update.effective_user.id
            print(f"🔍 DEBUG: user_id = {user_id}")

            user = self.db.get_user(user_id)
            print(f"🔍 DEBUG: user = {user}")

            if not user:
                print("❌ DEBUG: Пользователь не найден")
                await update.message.reply_text("❌ Сначала используйте /start")
                return

            print(f"🔍 DEBUG: Пытаемся присоединиться к игре {game_code}")
            success, message = self.db.join_game(game_code, user_id)

            if success:
                # Получаем информацию об игре
                game = self.db.get_game(game_code)
                bet_amount = game[3]
                player1_id = game[15]  # ⬅️ ИСПРАВЛЕННЫЙ ИНДЕКС

                # Клавиатура для броска костей
                keyboard = [[InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game[0]}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                # Уведомляем создателя игры (временно отключено)
                try:
                    await context.bot.send_message(
                        chat_id=player1_id,
                        text=f"✅ Игрок присоединился к игре {game_code}!\nГотовы бросить кости?",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    print(f"❌ Ошибка уведомления создателя: {e}")

                await update.message.reply_text(
                    f"✅ Вы присоединились к игре {game_code}!\n"
                    f"💰 Ставка: ${bet_amount:.0f}\n"
                    f"🎲 Готовы бросить кости?",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(f"❌ {message}")

        except (IndexError, ValueError) as e:
            print(f"❌ Ошибка в join_command: {e}")
            await update.message.reply_text(
                "Использование: /join <КОД_ИГРЫ>\n\n"
                "Пример:\n"
                "`/join A1B2C3`\n\n"
                "Код игры состоит из 6 букв и цифр",
                parse_mode='Markdown'
            )

    async def deposit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat

        # Блокируем команду в групповых чатах
        if chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "❌ Пополнение баланса доступно только через меню в личном чате с ботом.\n\n"
                "Перейдите в диалог с ботом и используйте кнопку 'Пополнить баланс'."
            )
            return

        # Блокируем прямое использование команды /deposit
        await update.message.reply_text(
            "💳 Для пополнения баланса используйте меню:\n\n"
            "1. Нажмите /menu\n"
            "2. Выберите 'Пополнить баланс'\n"
            "3. Выберите сумму пополнения"
        )

    async def create_game(self, query, bet_amount):
        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        print(f"🔍 BOT: create_game для user_id {user_id}, баланс: {user[4] if user else 'NO USER'}")

        if not user:
            await query.edit_message_text("Ошибка: пользователь не найден")
            return

        current_balance = user[4]

        if current_balance < bet_amount:
            await query.edit_message_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${current_balance:.0f}\n"
                f"Требуется: ${bet_amount:.0f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                    [InlineKeyboardButton("Назад", callback_data="find_game")]
                ])
            )
            return

        # Создаем игру
        game_id, game_code = self.db.create_game(user_id, bet_amount)

        # Резервируем средства
        self.db.update_balance(user_id, -bet_amount)

        # Кнопка для броска костей создателю
        keyboard = [
            [InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game_id}")],
            [InlineKeyboardButton("❌ Отменить игру", callback_data=f"cancel_active_game_{game_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Сообщение для создателя игры С КНОПКОЙ
        await query.edit_message_text(
            f"🎲 Игра создана!\n"
            f"💰 Ставка: ${bet_amount:.0f}\n\n"
            f"🆔 Код игры: `{game_code}`\n\n"
            "📤 **Отправьте приглашение другу!**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Отправляем приглашение для пересылки
        await self.send_game_invite(game_id, game_code, bet_amount, query)

        print(f"🔍 DEBUG: Приглашение для игры {game_code} отправлено")


    async def send_game_invite(self, game_id, game_code, bet_amount, creator_query):
        """Создает и отправляет приглашение для присоединения к игре 1 на 1"""
        print(f"🔍 DEBUG: send_game_invite для игры {game_code}")

        try:
            # Получаем информацию о боте
            bot_info = await self.application.bot.get_me()
            bot_username = bot_info.username

            # Создаем глубокую ссылку для быстрого присоединения
            deep_link_url = f"https://t.me/{bot_username}?start=join_{game_code}"

            # Сообщение с текстовой ссылкой
            invite_text = (
                f"🎲 **Приглашение в игру!**\n\n"
                f"💰 Ставка: ${bet_amount:.0f}\n"
                f"🎯 Формат: 1 на 1\n"
                f"🆔 Код: `{game_code}`\n\n"
                f"🎯 [Присоединиться к игре]({deep_link_url})\n\n"
                f"💰 *Победитель забирает ${bet_amount * 2 * 0.92:.0f} (за вычетом комиссии 8%)*"
            )

            # Инструкция для создателя
            instruction_text = (
                f"📤 **Отправьте это сообщение другу!**\n\n"
                f"Просто перешлите сообщение ниже - друг сможет присоединиться по ссылке."
            )

            await creator_query.message.reply_text(instruction_text, parse_mode='Markdown')

            # Отправляем приглашение с текстовой ссылкой
            await creator_query.message.reply_text(
                invite_text,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            print(f"🔍 DEBUG: Приглашение для игры {game_code} отправлено успешно!")

        except Exception as e:
            print(f"❌ DEBUG: Ошибка в send_game_invite: {e}")
            # Запасной вариант
            await creator_query.message.reply_text(
                f"🎲 Приглашение в игру!\n\n"
                f"💰 Ставка: ${bet_amount:.0f}\n"
                f"🎯 Формат: 1 на 1\n"
                f"🆔 Код: {game_code}\n\n"
                f"Используйте команду: /join {game_code}"
            )


    async def cancel_game_creation(self, query):
        """Отмена создания новой игры"""
        user_id = query.from_user.id

        # Очищаем состояние ожидания ввода, если было
        if hasattr(query, '_bot') and query._bot:
            context = query._bot.context
            context.user_data.pop('waiting_for_bet', None)

        await self.show_main_menu(query)


    async def cancel_active_game(self, query, game_id):
        """Отмена активной игры (до присоединения второго игрока)"""
        user_id = query.from_user.id

        # Получаем игру из базы
        game = self.db.get_game_by_id(game_id)
        if not game:
            await query.edit_message_text("❌ Игра не найдена или уже завершена")
            return

        # Проверяем, что пользователь - создатель игры
        if game[15] != user_id:  # p1_tg_id
            await query.answer("❌ Только создатель игры может её отменить", show_alert=True)
            return

        # Проверяем, что второй игрок еще не присоединился
        if game[16] is not None:  # p2_tg_id
            await query.answer("❌ Нельзя отменить игру, к которой уже присоединился второй игрок", show_alert=True)
            return

        # Возвращаем средства создателю
        bet_amount = game[3]
        self.db.update_balance(user_id, bet_amount)

        # Удаляем игру из базы
        self.db.cancel_game(game_id)

        await query.edit_message_text(
            f"✅ Игра отменена\n💰 Ставка ${bet_amount:.0f} возвращена на ваш баланс",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Главное меню", callback_data="main_menu")]
            ])
        )


    async def join_from_deeplink(self, update: Update, context: ContextTypes.DEFAULT_TYPE, game_code):
        """Обработка быстрого присоединения через deep link"""
        print(f"🔍 DEBUG: join_from_deeplink для кода {game_code}")

        user_id = update.effective_user.id
        user = self.db.get_user(user_id)

        if not user:
            await update.message.reply_text("❌ Сначала используйте /start")
            return

        success, message = self.db.join_game(game_code, user_id)

        if success:
            game = self.db.get_game(game_code)
            bet_amount = game[3]

            keyboard = [[InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game[0]}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"✅ Вы присоединились к игре {game_code}!\n"
                f"💰 Ставка: ${bet_amount:.0f}\n"
                f"🎲 Готовы бросить кости?",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(f"❌ {message}")


    async def cancel_duel_in_chat(self, query, chat_id):
        """Отмена дуэли в групповом чате"""
        user_id = query.from_user.id

        # Проверяем дуэли в чатах
        duel = self.duels.get(chat_id)
        if not duel:
            await query.answer("❌ Дуэль не найдена или уже завершена", show_alert=True)
            return

        # Проверяем права - только создатель может отменить
        if duel["creator_id"] != user_id:
            await query.answer("❌ Только создатель дуэли может её отменить", show_alert=True)
            return

        # Проверяем, что дуэль еще не началась
        if duel["state"] != "waiting":
            await query.answer("❌ Нельзя отменить начавшуюся дуэль", show_alert=True)
            return

        # Возвращаем средства создателю
        bet_amount = duel["bet"]
        self.db.update_balance(user_id, bet_amount)

        # Удаляем дуэль
        del self.duels[chat_id]

        await query.edit_message_text(
            f"❌ Дуэль отменена создателем\n💰 Ставка ${bet_amount:.0f} возвращена"
        )


    async def roll_dice(self, query, game_id, context):
        user_id = query.from_user.id

        # Отправляем анимированные кости
        dice_message = await query.message.reply_dice(emoji="🎲")

        # Получаем результат броска (значение от 1 до 6)
        dice_value = dice_message.dice.value

        # Сохраняем бросок в базу
        roll_data = self.db.save_dice_roll(game_id, user_id, dice_value)

        if not roll_data:
            await query.message.reply_text("❌ Ошибка: игра не найдена")
            return

        # Ждем немного чтобы анимация завершилась
        await asyncio.sleep(3)

        # Формируем сообщение с результатом
        current_rolls = roll_data['current_rolls']
        rolls_count = roll_data['rolls_count']
        total_so_far = sum(current_rolls)

        message_text = (
            f"🎯 Бросок {rolls_count}/3\n"
            f"🎲 Выпало: {dice_value}\n\n"
            f"📊 Ваши броски: {', '.join(map(str, current_rolls))}\n"
            f"💰 Сумма: {total_so_far}\n"
        )

        # Проверяем статус игры
        if rolls_count < 3:
            # Еще есть броски
            message_text += f"\nОсталось бросков: {3 - rolls_count}"
            keyboard = [[InlineKeyboardButton("🎲 Бросить снова", callback_data=f"roll_{game_id}")]]
        else:
            # Игрок завершил все 3 броска
            message_text += "\n✅ Вы завершили все броски!"
            keyboard = [[InlineKeyboardButton("⏳ Ожидаем соперника", callback_data="waiting")]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем результат
        await query.message.reply_text(message_text, reply_markup=reply_markup)

        # Проверяем, оба ли игрока завершили броски
        if self.db.check_both_players_finished(game_id):
            # Вычисляем финальные суммы
            player1_total, player2_total = self.db.calculate_final_scores(game_id)

            # Завершаем игру с выплатами
            result = self.db.finish_game(game_id, self.crypto_pay)
            await self.send_game_result(context, game_id, result)

    async def send_game_result(self, context, game_id, result):
        """Отправляет результаты игры обоим игрокам"""
        # Получаем игру по ID (а не по коду)
        game = self.db.get_game_by_id(game_id)  # Нужно создать этот метод!

        if not game:
            print(f"❌ Ошибка: игра с ID {game_id} не найдена")
            return

        p1_total = result['player1_total']
        p2_total = result['player2_total']
        winner_id = result['winner_id']
        winner_prize = result['winner_prize']
        commission = result['commission']
        check_result = result.get('check_result', {})

        # Получаем данные игроков для красивого отображения
        p1_id = game[15]  # p1_tg_id на 15 позиции
        p2_id = game[16]  # p2_tg_id на 16 позиции
        p1_username = game[17] or "Игрок 1"  # p1_username
        p2_username = game[18] or "Игрок 2"  # p2_username

        player1_name = f"@{p1_username}" if p1_username and p1_username != "Игрок 1" else "Игрок 1"
        player2_name = f"@{p2_username}" if p2_username and p2_username != "Игрок 2" else "Игрок 2"

        # ... остальной код без изменений

        if winner_id:
            winner_name = player1_name if winner_id == p1_id else player2_name

            if check_result and check_result.get('ok'):
                pay_url = check_result['result']['pay_url']

                # Сообщение ПОБЕДИТЕЛЮ с чеком
                winner_text = (
                    f"🏆 ПОБЕДА!\n\n"
                    f"🎲 {player1_name}: {p1_total}\n"
                    f"🎲 {player2_name}: {p2_total}\n\n"
                    f"💰 Ваш выигрыш: ${winner_prize:.2f}\n\n"
                    f"💸 Комиссия системы: 8%\n\n"
                    f"📎 Нажмите кнопку ниже чтобы получить выигрыш:"
                )

                await context.bot.send_message(
                    chat_id=winner_id,
                    text=winner_text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💰 ПОЛУЧИТЬ ВЫИГРЫШ", url=pay_url)]
                    ])
                )

                # Сообщение ПРОИГРАВШЕМУ
                loser_id = p2_id if winner_id == p1_id else p1_id
                loser_text = (
                    f"💔 Поражение\n\n"
                    f"🎲 {player1_name}: {p1_total}\n"
                    f"🎲 {player2_name}: {p2_total}\n\n"
                    f"🏆 Победитель: {winner_name}\n"
                    f"💰 Выигрыш: ${winner_prize:.2f}\n\n"
                    f"Спасибо за игру! 🎲"
                )

                await context.bot.send_message(chat_id=loser_id, text=loser_text)

            else:
                # Ошибка создания чека
                error_text = (
                    f"🎲 Игра завершена!\n\n"
                    f"🎲 {player1_name}: {p1_total}\n"
                    f"🎲 {player2_name}: {p2_total}\n\n"
                    f"🏆 Победитель: {winner_name}\n"
                    f"❌ Ошибка выплаты. Средства возвращены."
                )
                await context.bot.send_message(chat_id=p1_id, text=error_text)
                await context.bot.send_message(chat_id=p2_id, text=error_text)

        else:
            # Ничья
            draw_text = (
                f"🤝 Ничья!\n\n"
                f"🎲 {player1_name}: {p1_total}\n"
                f"🎲 {player2_name}: {p2_total}\n\n"
                f"💰 Ставки возвращены игрокам"
            )
            await context.bot.send_message(chat_id=p1_id, text=draw_text)
            await context.bot.send_message(chat_id=p2_id, text=draw_text)

    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat = update.effective_chat

        # Блокируем меню в групповых чатах
        if chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "❌ Меню доступно только в личном чате с ботом.\n\n"
                "Перейдите в диалог с ботом для управления настройками."
            )
            return

        self.db.register_user(user.id, user.username, user.first_name)

        # Получаем статистику для показа в меню
        stats = self.db.get_user_stats(user.id)
        balance = stats[1] if stats else 0

        menu_text = (
            f"🎲 Главное меню\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            "Выберите действие:"
        )

        # ОБНОВЛЕННАЯ КЛАВИАТУРА С КНОПКОЙ ЛОББИ
        keyboard = [
            [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
            [InlineKeyboardButton("👥 Создать лобби", callback_data="create_lobby_menu")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(menu_text, reply_markup=reply_markup)


    def _gen_lobby_id(self) -> str:
        """Генерируем короткий уникальный id для лобби"""
        return uuid.uuid4().hex[:8]

    async def show_lobby_options(self, query):
        """Показывает выбор ставки для лобби"""
        keyboard = [
            [InlineKeyboardButton("$1", callback_data="lobby_bet_1")],
            [InlineKeyboardButton("$5", callback_data="lobby_bet_5")],
            [InlineKeyboardButton("$10", callback_data="lobby_bet_10")],
            [InlineKeyboardButton("$25", callback_data="lobby_bet_25")],
            [InlineKeyboardButton("$50", callback_data="lobby_bet_50")],
            [InlineKeyboardButton("$100", callback_data="lobby_bet_100")],
            [InlineKeyboardButton("💵 Произвольная ставка", callback_data="lobby_custom_bet")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "👥 **Создание мультиплеерного лобби**\n\n"
            "💰 Выберите сумму ставки для каждого игрока:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def create_lobby_command(self, update, context):
        """Команда /create — показывает выбор ставки для лобби."""
        chat = update.effective_chat

        # Блокируем в групповых чатах
        if chat.type in ["group", "supergroup"]:
            await update.message.reply_text(
                "❌ Создание лобби доступно только в личном чате с ботом.\n\n"
                "Перейдите в диалог с ботом и используйте меню."
            )
            return

        keyboard = [
            [InlineKeyboardButton("$1", callback_data="lobby_bet_1")],
            [InlineKeyboardButton("$5", callback_data="lobby_bet_5")],
            [InlineKeyboardButton("$10", callback_data="lobby_bet_10")],
            [InlineKeyboardButton("$25", callback_data="lobby_bet_25")],
            [InlineKeyboardButton("$50", callback_data="lobby_bet_50")],
            [InlineKeyboardButton("$100", callback_data="lobby_bet_100")],
            [InlineKeyboardButton("💵 Произвольная ставка", callback_data="lobby_custom_bet")],
            [InlineKeyboardButton("❌ Отмена", callback_data="lobby_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "👥 **Создание лобби**\n\nВыберите сумму ставки для каждого игрока:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


    async def _handle_create_lobby_cb(self, update, context):
        """Обработка нажатий кнопок создания лобби (3/4/5 игроков)."""
        query = update.callback_query
        await query.answer()

        data = query.data  # create_lobby:3
        parts = data.split(":")

        if len(parts) != 2:
            await query.edit_message_text("Ошибка выбора лобби.")
            return

        if parts[1] == "cancel":
            await query.edit_message_text("Создание лобби отменено.")
            return

        # Определяем количество игроков
        try:
            max_players = int(parts[1])
        except:
            await query.edit_message_text("Неверный формат выбора.")
            return

        # Создаём новый lobby_id
        lobby_id = self._gen_lobby_id()

        creator = query.from_user

        # Структура лобби
        lobby = {
            "id": lobby_id,
            "creator_id": creator.id,
            "creator_name": creator.username or creator.first_name,
            "max_players": max_players,
            "players": [{
                "id": creator.id,
                "username": creator.username or creator.first_name,
                "ready": False
            }],
            "timer_started": False,
            "timer_expires_at": None,
            "message_chat_id": query.message.chat.id,
            "message_id": None
        }

        # Сохраняем лобби
        self.lobbies[lobby_id] = lobby

        # Отправляем основное сообщение лобби
        text = self._lobby_text(lobby)
        keyboard = self._lobby_keyboard(lobby)

        sent_message = await query.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # сохраняем ID сообщения
        lobby["message_id"] = sent_message.message_id

    async def _handle_lobby_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data  # форматы: lobby_toggle_ready:lobbyid:userid, lobby_start:lobbyid, lobby_leave:lobbyid

        print(f"🔍 DEBUG _handle_lobby_callbacks: data='{data}'")

        parts = data.split(":")

        # Проверяем что есть достаточно частей
        if len(parts) < 2:
            print(f"❌ Ошибка: неверный формат данных лобби: {data}")
            await query.answer("❌ Ошибка формата данных", show_alert=True)
            return

        action = parts[0]
        lobby_id = parts[1]

        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            await query.edit_message_text("❌ Лобби не найдено или уже началось.")
            return

        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name

        if action == "lobby_toggle_ready":
            # Проверяем что есть третья часть (user_id)
            if len(parts) < 3:
                await query.answer("❌ Ошибка формата данных", show_alert=True)
                return

            player_id = int(parts[2])
            for p in lobby["players"]:
                if p["id"] == player_id:
                    p["ready"] = not p["ready"]
                    break

            # Если все готовы и таймер еще не запущен — запускаем
            all_ready = all(p["ready"] for p in lobby["players"]) and len(lobby["players"]) == lobby["max_players"]
            if all_ready and not lobby["timer_started"]:
                asyncio.create_task(self._start_lobby_timer(lobby_id, context))

        elif action == "lobby_start":
            # Запуск игры владельцем, если все готовы
            if user_id != lobby["creator_id"]:
                await query.answer("Только владелец может начать игру", show_alert=True)
                return

            all_ready = all(p["ready"] for p in lobby["players"]) and len(lobby["players"]) == lobby["max_players"]
            if not all_ready:
                await query.answer("Все игроки должны быть готовы", show_alert=True)
                return

            await self._start_game(lobby_id, context)
            return

        elif action == "lobby_leave":
            # Игрок выходит из лобби
            leaving_player = next((p for p in lobby["players"] if p["id"] == user_id), None)

            # Возвращаем ставку если игрок оплатил
            if leaving_player and leaving_player.get("paid") and "bet_amount" in lobby:
                bet_amount = lobby["bet_amount"]
                self.db.update_balance(user_id, bet_amount)
                print(f"🔍 DEBUG: Возвращена ставка ${bet_amount:.0f} игроку {username}")

            lobby["players"] = [p for p in lobby["players"] if p["id"] != user_id]

            if not lobby["players"]:
                # Если лобби пустое — удаляем
                self.lobbies.pop(lobby_id)
                await query.message.delete()
                return

            # Если вышел владелец — передаем владельца другому игроку
            if user_id == lobby["creator_id"]:
                new_owner = lobby["players"][0]
                lobby["creator_id"] = new_owner["id"]
                lobby["creator_name"] = new_owner["username"]

        # Обновляем сообщение
        text = self._lobby_text(lobby)
        keyboard = self._lobby_keyboard(lobby)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")


    async def _handle_join_lobby_cb(self, update, context):
        """Обработка нажатия кнопки присоединения к лобби"""
        query = update.callback_query
        await query.answer()

        lobby_id = query.data.split(":")[1]
        user_id = query.from_user.id
        username = query.from_user.username or query.from_user.first_name

        print(f"🔍 DEBUG: Присоединение к лобби {lobby_id} пользователем {username}")

        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            await query.edit_message_text("❌ Лобби не найдено или уже началось")
            return

        # Проверяем, не присоединился ли уже
        if any(player["id"] == user_id for player in lobby["players"]):
            await query.answer("❌ Вы уже в этом лобби!", show_alert=True)
            return

        # Проверяем, есть ли свободные места
        if len(lobby["players"]) >= lobby["max_players"]:
            await query.answer("❌ Лобби заполнено!", show_alert=True)
            return

        # Проверяем баланс для ставки
        bet_amount = lobby.get('bet_amount', 0)
        user = self.db.get_user(user_id)
        if not user or user[4] < bet_amount:
            await query.answer(f"❌ Недостаточно средств! Нужно: ${bet_amount:.0f}", show_alert=True)
            return

        # Списываем ставку
        self.db.update_balance(user_id, -bet_amount)

        # Добавляем игрока в лобби
        lobby["players"].append({
            "id": user_id,
            "username": username,
            "ready": False,
            "paid": True
        })

        await query.answer(f"✅ Вы присоединились к лобби! Ставка ${bet_amount:.0f} списана.", show_alert=True)

        # Обновляем сообщение лобби
        await self._update_lobby_message(lobby)

        # Отправляем уведомление создателю
        try:
            await context.bot.send_message(
                chat_id=lobby["creator_id"],
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!"
            )
        except:
            pass  # Игнорируем ошибку отправки

    async def create_lobby_with_bet(self, query, bet_amount, max_players):
        """Создает лобби с указанной ставкой и количеством игроков"""
        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        print(f"🔍 DEBUG: create_lobby_with_bet - bet_amount={bet_amount}, max_players={max_players}")

        if not user:
            await query.edit_message_text("❌ Пользователь не найден")
            return

        current_balance = user[4]
        required_balance = bet_amount

        if current_balance < required_balance:
            await query.edit_message_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${current_balance:.0f}\n"
                f"Требуется: ${required_balance:.0f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                    [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
                ])
            )
            return

        # Списываем ставку создателя
        self.db.update_balance(user_id, -bet_amount)

        # Создаём новый lobby_id
        lobby_id = self._gen_lobby_id()

        creator = query.from_user

        # Структура лобби с ставкой
        lobby = {
            "id": lobby_id,
            "creator_id": creator.id,
            "creator_name": creator.username or creator.first_name,
            "max_players": max_players,
            "bet_amount": bet_amount,
            "players": [{
                "id": creator.id,
                "username": creator.username or creator.first_name,
                "ready": False,
                "paid": True
            }],
            "timer_started": False,
            "timer_expires_at": None,
            "message_chat_id": query.message.chat.id,
            "message_id": None
        }

        # Сохраняем лобби
        self.lobbies[lobby_id] = lobby
        print(f"🔍 DEBUG: Лобби создано, ID: {lobby_id}")

        # Отправляем основное сообщение лобби
        text = self._lobby_text(lobby)
        keyboard = self._lobby_keyboard(lobby)

        sent_message = await query.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # сохраняем ID сообщения
        lobby["message_id"] = sent_message.message_id

        # ОТПРАВЛЯЕМ ПРИГЛАШЕНИЕ ДЛЯ ПЕРЕСЫЛКИ
        print(f"🔍 DEBUG: Вызываем send_lobby_invite для лобби {lobby_id}")
        await self.send_lobby_invite(lobby_id, query)

        # Простое сообщение о создании
        await query.edit_message_text(
            f"✅ Лобби создано!\n\n"
            f"💰 Ставка: ${bet_amount:.0f} с игрока\n"
            f"👥 Игроков: 1/{max_players}\n"
            f"🆔 Код: {lobby_id}\n\n"
            f"📤 Отправьте приглашение друзьям!",
            parse_mode='Markdown'
        )
        print(f"🔍 DEBUG: Сообщение о создании лобби отправлено")

    async def send_lobby_invite(self, lobby_id, creator_query):
        """Создает и отправляет приглашение для присоединения к лобби"""
        print(f"🔍 DEBUG: send_lobby_invite вызван для лобби {lobby_id}")

        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            print(f"❌ DEBUG: Лобби {lobby_id} не найдено")
            await creator_query.answer("❌ Лобби не найдено")
            return

        bet_amount = lobby.get('bet_amount', 0)
        total_bank = bet_amount * lobby['max_players']

        try:
            # Получаем username бота
            bot_info = await self.application.bot.get_me()
            bot_username = bot_info.username

            # Создаем глубокую ссылку для быстрого присоединения
            deep_link_url = f"https://t.me/{bot_username}?start=joinlobby_{lobby_id}"

            # Сообщение с текстовой ссылкой
            invite_text = (
                f"🎮 **Приглашение в лобби!**\n\n"
                f"👤 Создатель: {lobby['creator_name']}\n"
                f"💰 Ставка: ${bet_amount:.0f} с игрока\n"
                f"🏦 Общий банк: ${total_bank:.0f}\n"
                f"👥 Игроков: {len(lobby['players'])}/{lobby['max_players']}\n"
                f"🆔 Код: `{lobby_id}`\n\n"
                f"🎯 [Присоединиться]({deep_link_url})\n\n"
                f"💰 *Каждый игрок вносит ставку ${bet_amount:.0f}*"
            )

            print(f"🔍 DEBUG: Отправляем приглашение со ссылкой...")
            # Отправляем сообщение с текстовой ссылкой
            await creator_query.message.reply_text(
                invite_text,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            print(f"🔍 DEBUG: Приглашение отправлено успешно!")

        except Exception as e:
            print(f"❌ DEBUG: Ошибка в send_lobby_invite: {e}")
            # Запасной вариант без ссылки
            await creator_query.message.reply_text(
                f"🎮 Приглашение в лобби!\n\n"
                f"👤 Создатель: {lobby['creator_name']}\n"
                f"💰 Ставка: ${bet_amount:.0f}\n"
                f"👥 Игроков: {len(lobby['players'])}/{lobby['max_players']}\n"
                f"🆔 Код: {lobby_id}\n\n"
                f"Используйте команду: /join_lobby {lobby_id}"
            )


    def _lobby_text(self, lobby):
        players_text = "\n".join(
            f"{p['username']} — {'✅' if p['ready'] else '❌'}"
            for p in lobby["players"]
        )
        timer_info = ""
        if lobby["timer_started"]:
            left = max(0, int(lobby["timer_expires_at"] - time.time()))
            timer_info = f"\n\n⏳ Таймер: {left} сек"

        # Добавляем информацию о ставке
        bet_info = ""
        if "bet_amount" in lobby:
            bet_info = f"💰 Ставка: ${lobby['bet_amount']:.0f} с игрока\n"
            total_bank = lobby['bet_amount'] * lobby['max_players']
            bet_info += f"🏦 Общий банк: ${total_bank:.0f}\n"

        return (
            f"🎲 Лобби #{lobby['id']}\n"
            f"{bet_info}"
            f"👤 Владелец: {lobby['creator_name']}\n"
            f"👥 Игроки ({len(lobby['players'])}/{lobby['max_players']}):\n{players_text}"
            f"{timer_info}"
        )

    def _lobby_keyboard(self, lobby):
        buttons = []

        # Кнопки игроков "Готов" или "Не готов"
        for p in lobby["players"]:
            text = "Готов" if not p["ready"] else "Не готов"
            buttons.append([
                InlineKeyboardButton(
                    f"{text} ({p['username']})",
                    callback_data=f"lobby_toggle_ready:{lobby['id']}:{p['id']}"
                )
            ])

        # Кнопка "Начать игру" для создателя, если все готовы и достаточно игроков
        all_ready = all(p["ready"] for p in lobby["players"]) and len(lobby["players"]) == lobby["max_players"]
        if lobby["creator_id"] in [p["id"] for p in lobby["players"]] and all_ready:
            buttons.append([InlineKeyboardButton("▶️ Начать игру", callback_data=f"lobby_start:{lobby['id']}")])

        # Кнопка выйти из лобби
        buttons.append([InlineKeyboardButton("❌ Выйти из лобби", callback_data=f"lobby_leave:{lobby['id']}")])

        return InlineKeyboardMarkup(buttons)


    async def show_lobby_size_options(self, query, bet_amount):
        """Показывает выбор количества игроков после выбора ставки"""
        keyboard = [
            [InlineKeyboardButton("👥 3 игрока", callback_data=f"lobby_size_{bet_amount}_3")],
            [InlineKeyboardButton("👥 4 игрока", callback_data=f"lobby_size_{bet_amount}_4")],
            [InlineKeyboardButton("👥 5 игроков", callback_data=f"lobby_size_{bet_amount}_5")],
            [InlineKeyboardButton("🔙 Назад к ставке", callback_data="create_lobby_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"👥 **Создание лобби**\n\n"
            f"💰 Ставка: **${bet_amount:.0f}** с игрока\n\n"
            "Выберите количество игроков:\n"
            "• 3 игрока - быстрые игры\n"
            "• 4 игрока - оптимальный вариант\n"
            "• 5 игроков - масштабные баталии\n\n"
            f"💰 **Общий банк:** ${bet_amount * 3:.0f}-${bet_amount * 5:.0f}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def ask_custom_lobby_bet(self, query):
        """Запрашиваем произвольную сумму ставки для лобби"""
        await query.edit_message_text(
            "💵 Введите сумму ставки для каждого игрока (минимум $1):\n\n"
            "Пример: 15 или 75.5\n\n"
            "💰 Каждый игрок будет вносить эту сумму",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
            ])
        )

    async def show_lobby_size_options_from_message(self, update, bet_amount):
        """Показывает выбор размера лобби после кастомной ставки из сообщения"""
        keyboard = [
            [InlineKeyboardButton("👥 3 игрока", callback_data=f"lobby_size_{bet_amount}_3")],
            [InlineKeyboardButton("👥 4 игрока", callback_data=f"lobby_size_{bet_amount}_4")],
            [InlineKeyboardButton("👥 5 игроков", callback_data=f"lobby_size_{bet_amount}_5")],
            [InlineKeyboardButton("🔙 Назад", callback_data="create_lobby_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"👥 **Создание лобби**\n\n"
            f"💰 Ставка: **${bet_amount:.0f}** с игрока\n\n"
            "Выберите количество игроков:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


    async def join_lobby_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для присоединения к лобби по ID"""
        chat = update.effective_chat

        # Блокируем в групповых чатах
        if chat.type in ["group", "supergroup"]:
            await update.message.reply_text("❌ Присоединение к лобби доступно только в личном чате")
            return

        if not context.args:
            await update.message.reply_text("Использование: /join_lobby <ID_лобби>")
            return

        lobby_id = context.args[0]
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        print(f"🔍 DEBUG: Присоединение к лобби {lobby_id} через команду")

        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            await update.message.reply_text("❌ Лобби не найдено или уже началось")
            return

        # Проверяем, не присоединился ли уже
        if any(player["id"] == user_id for player in lobby["players"]):
            await update.message.reply_text("❌ Вы уже в этом лобби!")
            return

        # Проверяем, есть ли свободные места
        if len(lobby["players"]) >= lobby["max_players"]:
            await update.message.reply_text("❌ Лобби заполнено!")
            return

        # Проверяем баланс для ставки
        bet_amount = lobby.get('bet_amount', 0)
        user = self.db.get_user(user_id)
        if not user or user[4] < bet_amount:
            await update.message.reply_text(f"❌ Недостаточно средств! Нужно: ${bet_amount:.0f}")
            return

        # Списываем ставку
        self.db.update_balance(user_id, -bet_amount)

        # Добавляем игрока в лобби
        lobby["players"].append({
            "id": user_id,
            "username": username,
            "ready": False,
            "paid": True
        })

        await update.message.reply_text(f"✅ Вы присоединились к лобби #{lobby_id}! Ставка ${bet_amount:.0f} списана.")

        # Обновляем сообщение лобби
        await self._update_lobby_message(lobby)

        # Отправляем уведомление создателю
        try:
            await context.bot.send_message(
                chat_id=lobby["creator_id"],
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!"
            )
        except:
            pass

    async def _handle_copy_lobby_cb(self, update, context):
        """Показывает команду для копирования"""
        query = update.callback_query
        await query.answer()

        lobby_id = query.data.split(":")[1]

        await query.edit_message_text(
            f"📋 **Команда для присоединения к лобби:**\n\n"
            f"`/join_lobby {lobby_id}`\n\n"
            "Просто скопируй и отправь другу!",
            parse_mode='Markdown'
        )


    # Вспомогательные async-функции:
    async def _update_lobby_message(self, lobby):
        """Обновляет текст/клавиатуру сообщения с лобби."""
        try:
            text = self._lobby_text(lobby)
            keyboard = self._lobby_keyboard(lobby)
            await self.application.bot.edit_message_text(
                chat_id=lobby["message_chat_id"],
                message_id=lobby["message_id"],
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            # не критично: логируем, но продолжаем
            print("Ошибка обновления лобби:", e)

    async def _notify_creator_ready_all(self, lobby):
        """Если все готовы, уведомим создателя (он может нажать Start) — можно также автозапустить."""
        try:
            chat_id = lobby["message_chat_id"]
            creator_id = lobby["creator_id"]
            await self.application.bot.send_message(chat_id=chat_id,
                                                    text=f"Все игроки в лобби #{lobby['id']} готовы. Создатель @{lobby['creator_name']} может нажать «Начать игру» или игра начнётся автоматически.",
                                                    )
        except Exception as e:
            print("notify error:", e)

    async def _start_lobby_timer(self, lobby_id, context: ContextTypes.DEFAULT_TYPE):
        lobby = self.lobbies.get(lobby_id)
        if not lobby or lobby["timer_started"]:
            return

        lobby["timer_started"] = True
        lobby["timer_expires_at"] = time.time() + 30  # 30 секунд таймер

        while True:
            now = time.time()
            if now >= lobby["timer_expires_at"]:
                # Таймер истек — запускаем игру
                await self._start_game(lobby_id, context)
                break

            # Обновляем сообщение с таймером
            chat_id = lobby["message_chat_id"]
            message_id = lobby["message_id"]
            text = self._lobby_text(lobby)
            keyboard = self._lobby_keyboard(lobby)

            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception:
                # Игнорируем ошибки редактирования (например, если сообщение уже удалено)
                pass

            await asyncio.sleep(1)

    async def _start_game(self, lobby_id, context):
        lobby = self.lobbies.pop(lobby_id, None)
        if not lobby:
            return

        chat_id = lobby["message_chat_id"]
        players = lobby["players"]

        # Создаём структуру игры
        game_id = lobby_id  # для простоты совпадает с lobby_id

        # Сохраняем состояние игры в self.games или в БД (зависит от реализации)
        self.games[game_id] = {
            "players": players,
            "current_player_index": 0,
            "rolls": {p["id"]: [] for p in players},  # броски каждого игрока
            "chat_id": chat_id,
            "started_at": time.time(),
            "lobby_data": lobby  # Сохраняем данные лобби для выплат
        }

        first_player = players[0]

        # Отправляем сообщение с началом игры и кнопкой "Бросить кости"
        text = (
            f"🚀 Игра в лобби #{lobby_id} началась!\n\n"
            f"💰 Ставка: ${lobby.get('bet_amount', 0):.0f} с игрока\n"
            f"🏦 Общий банк: ${lobby.get('bet_amount', 0) * len(players):.0f}\n\n"
            f"Ходит игрок: <b>{first_player['username']}</b>\n"
            f"Нажмите кнопку, чтобы бросить кубики (3 броска на игрока)."
        )

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎲 Бросить кубики", callback_data=f"roll_{game_id}:{first_player['id']}")
        ]])

        await context.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")


    async def join_lobby_from_deeplink(self, update: Update, context: ContextTypes.DEFAULT_TYPE, lobby_id: str):
        """Обработка присоединения к лобби через глубокую ссылку"""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name

        print(f"🔍 DEBUG: Присоединение к лобби {lobby_id} через глубокую ссылку")

        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            await update.message.reply_text("❌ Лобби не найдено или уже началось")
            return

        # Проверяем, не присоединился ли уже
        if any(player["id"] == user_id for player in lobby["players"]):
            await update.message.reply_text("❌ Вы уже в этом лобби!")
            return

        # Проверяем, есть ли свободные места
        if len(lobby["players"]) >= lobby["max_players"]:
            await update.message.reply_text("❌ Лобби заполнено!")
            return

        # Проверяем баланс для ставки
        bet_amount = lobby.get('bet_amount', 0)
        user = self.db.get_user(user_id)
        if not user or user[4] < bet_amount:
            await update.message.reply_text(f"❌ Недостаточно средств! Нужно: ${bet_amount:.0f}")
            return

        # Списываем ставку
        self.db.update_balance(user_id, -bet_amount)

        # Добавляем игрока в лобби
        lobby["players"].append({
            "id": user_id,
            "username": username,
            "ready": False,
            "paid": True
        })

        await update.message.reply_text(
            f"✅ Вы присоединились к лобби #{lobby_id}!\n"
            f"💰 Ставка ${bet_amount:.0f} списана\n\n"
            f"👥 Игроков: {len(lobby['players'])}/{lobby['max_players']}\n"
            f"Ожидайте начала игры!"
        )

        # Обновляем сообщение лобби
        await self._update_lobby_message(lobby)

        # Отправляем уведомление создателю
        try:
            await context.bot.send_message(
                chat_id=lobby["creator_id"],
                text=f"🎮 Игрок {username} присоединился к вашему лобби #{lobby_id}!"
            )
        except:
            pass


    async def roll_dice_in_lobby(self, query, lobby_id, user_id):
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            await query.answer("Лобби не найдено или игра уже началась", show_alert=True)
            return

        # Проверяем, что игрок в лобби
        player = next((p for p in lobby["players"] if p["id"] == user_id), None)
        if not player:
            await query.answer("Вы не в этом лобби", show_alert=True)
            return

        # Проверяем, что игрок еще не бросил кость в этом раунде
        if player.get("rolled"):
            await query.answer("Вы уже бросали кости в этом раунде", show_alert=True)
            return

        # Бросок кости (от 1 до 6)
        dice_value = random.randint(1, 6)
        player["rolled"] = True
        player["last_roll"] = dice_value

        # Отправляем анимированные кости
        await query.message.reply_dice(emoji="🎲")

        # Формируем статус лобби с результатами
        status_lines = []
        all_rolled = True
        for p in lobby["players"]:
            roll_str = f"{p['last_roll']}" if p.get("rolled") else "–"
            status_lines.append(f"{p['username']} 🎲: {roll_str}")
            if not p.get("rolled"):
                all_rolled = False

        status_text = (
                f"🎲 Результаты бросков:\n" + "\n".join(status_lines)
        )

        keyboard = []
        if all_rolled:
            keyboard.append(
                [InlineKeyboardButton("🚀 Начать следующий раунд", callback_data=f"lobby_next_round:{lobby_id}")])
        else:
            keyboard.append([InlineKeyboardButton("⏳ Ожидаем броски остальных", callback_data="waiting")])

        await query.message.reply_text(status_text, reply_markup=InlineKeyboardMarkup(keyboard))

        # Если все бросили, запускаем таймер на 30 секунд
        if all_rolled and not lobby.get("timer_started"):
            lobby["timer_started"] = True
            lobby["timer_expires_at"] = time.time() + 30

            async def timer_finish():
                await asyncio.sleep(30)
                if lobby_id in self.lobbies:
                    await self._start_game(lobby_id, query._bot)  # или context.bot, в зависимости от вызова

            asyncio.create_task(timer_finish())


    async def _start_game_after_delay(self, lobby_id, delay):
        await asyncio.sleep(delay)
        lobby = self.lobbies.get(lobby_id)
        if not lobby:
            return  # лобби могло удалиться

        players = lobby["players"]
        if all(player.get("ready", False) for player in players):
            await self._start_game(lobby_id)
        else:
            # Если кто-то отписался/не готов, сбрасываем таймер
            lobby["timer_started"] = False
            lobby["timer_expires_at"] = None
            # Обновляем сообщение лобби с актуальным состоянием
            chat_id = lobby["message_chat_id"]
            message_id = lobby["message_id"]
            text = self._lobby_text(lobby)
            keyboard = self._lobby_keyboard(lobby, all_ready=False)
            await self.application.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
            reply_markup=keyboard, parse_mode="HTML")

    # =======================  Д У Э Л И  (полная версия) ==========================

    async def duel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        /duel <ставка>
        - Создаёт дуэль в групповом чате
        - Принимает вызов
        - Списывает баланс
        - Запускает игру
        """
        print(f"🔍 DEBUG duel_command: начат в чате {update.effective_chat.id}")

        chat = update.effective_chat
        chat_id = chat.id
        user = update.effective_user

        if chat.type == "private":
            await update.message.reply_text("Эта команда работает только в групповом чате.")
            return

        if not context.args:
            await update.message.reply_text("Использование: /duel <ставка>\nПример: /duel 10")
            return

        # Ставка
        try:
            bet = float(context.args[0])
            if bet <= 0:
                raise ValueError
        except:
            await update.message.reply_text("Корректный пример: /duel 10")
            return

        # Инициализируем контейнер дуэлей
        if not hasattr(self, "duels"):
            self.duels = {}

        duel = self.duels.get(chat_id)

        # ─────────────────────── СОЗДАНИЕ ДУЭЛИ ───────────────────────
        if duel is None:
            # Проверяем баланс создателя
            u = self.db.get_user(user.id)
            if not u or u[4] < bet:
                await update.message.reply_text("❌ Недостаточно средств для дуэли.")
                return

            # Списываем (резервируем) ставку
            self.db.update_balance(user.id, -bet)

            self.duels[chat_id] = {
                "bet": bet,
                "creator_id": user.id,
                "creator_name": user.username or user.first_name,
                "opponent_id": None,
                "opponent_name": None,
                "state": "waiting",
                "game": None,
                "message_id": update.message.message_id
            }

            keyboard = [
                [InlineKeyboardButton("❌ Отменить дуэль", callback_data=f"cancel_duel_{chat_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                f"🎯 @{user.username or user.first_name} вызывает дуэль на ${bet}!\n\n"
                f"Чтобы принять — напишите в чат:\n/duel {bet}",
                reply_markup=reply_markup
            )
            return

        # ─────────────────────── ПРИЁМ ДУЭЛИ ───────────────────────
        if duel["state"] == "waiting":
            if bet != duel["bet"]:
                await update.message.reply_text(
                    f"Здесь уже есть дуэль на ${duel['bet']}.\n"
                    f"Для принятия напиши: /duel {duel['bet']}"
                )
                return

            if user.id == duel["creator_id"]:
                await update.message.reply_text("Ты уже создал эту дуэль.")
                return

            # Проверяем баланс оппонента
            u = self.db.get_user(user.id)
            if not u or u[4] < bet:
                await update.message.reply_text("❌ Недостаточно средств для дуэли.")
                return

            # Списание ставки второго игрока
            self.db.update_balance(user.id, -bet)

            duel["opponent_id"] = user.id
            duel["opponent_name"] = user.username or user.first_name
            duel["state"] = "in_progress"

            # Инициализация игры
            duel["game"] = {
                "players": [
                    {"id": duel["creator_id"], "username": duel["creator_name"]},
                    {"id": duel["opponent_id"], "username": duel["opponent_name"]},
                ],
                "current_index": 0,
                "rolls": {duel["creator_id"]: [], duel["opponent_id"]: []},
                "chat_id": chat_id
            }

            await update.message.reply_text(
                f"🔥 Дуэль началась!\n\n"
                f"👤 @{duel['creator_name']} vs @{duel['opponent_name']}\n"
                f"Ставка: ${bet}\n"
                f"Первым ходит @{duel['creator_name']}"
            )

            await self.send_duel_roll_prompt(chat_id, duel["creator_id"])
            return

        # ─────────────────────── ЕСЛИ ДУЭЛЬ УЖЕ ИДЁТ ───────────────────────
        await update.message.reply_text("⚠ В этом чате уже идёт дуэль.")


    async def handle_duel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat = update.effective_chat
        user = update.effective_user
        text = update.message.text.split()

        # Только в группах
        if chat.type not in ["group", "supergroup"]:
            await update.message.reply_text("❌ Дуэли доступны только в группах.")
            return

        # Проверка аргументов
        if len(text) != 2:
            await update.message.reply_text("Использование: /duel 10")
            return

        try:
            bet = int(text[1])
            if bet < 1:
                raise ValueError
        except:
            await update.message.reply_text("❌ Неверная сумма ставки")
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚔ Принять дуэль", callback_data="duel_accept")],
            [InlineKeyboardButton("❌ Отмена", callback_data="duel_cancel")]
        ])

        # Создаём сообщение вызова
        msg = await update.message.reply_text(
            f"⚔ <b>{user.first_name}</b> вызывает на дуэль!\n"
            f"💰 Ставка: {bet}$\n\n"
            f"Чтобы принять — нажмите кнопку ниже.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

        # Сохраняем дуэль по message_id
        self.active_duels[msg.message_id] = {
            "bet": bet,
            "p1": user.id,
            "p2": None,
            "status": "waiting",
            "rolls": {},
            "chat_id": chat.id,
            "msg_id": msg.message_id,
            "turn": None
        }

    # --------------------------------------------------------------------

    async def send_duel_roll_prompt(self, chat_id: int, user_id: int):
        """Показывает кнопку броска для конкретного игрока с проверками"""
        print(f"🔍 DEBUG send_duel_roll_prompt: chat_id={chat_id}, user_id={user_id}")

        try:
            # Проверяем, что дуэль еще существует
            duel = self.duels.get(chat_id)
            if not duel or duel["state"] != "in_progress":
                print(f"🔍 DEBUG: Дуэль не найдена или завершена")
                return

            # Создаем кнопку с данными для проверок
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Бросить кости", callback_data=f"duel_roll:{chat_id}:{user_id}")
            ]])

            # Получаем имя игрока для красивого отображения
            player_name = "игрока"
            if duel.get("creator_id") == user_id:
                player_name = duel.get("creator_name", "игрока")
            elif duel.get("opponent_id") == user_id:
                player_name = duel.get("opponent_name", "игрока")

            message = await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"🎲 Ход <a href='tg://user?id={user_id}'>{player_name}</a>\nНажмите кнопку чтобы бросить кости:",
                reply_markup=kb,
                parse_mode="HTML"
            )
            print(f"🔍 DEBUG: Кнопка броска отправлена для {player_name}")

        except Exception as e:
            print(f"❌ Ошибка отправки запроса на бросок: {e}")

    # --------------------------------------------------------------------

    async def duel_roll_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        print(
            f"🔍 DEBUG duel_roll_handler: data='{query.data}', user_id={query.from_user.id}, chat_id={query.message.chat.id}")

        try:
            user_id = query.from_user.id
            chat_id = query.message.chat.id

            # Парсим данные из callback_data
            parts = query.data.split(':')
            if len(parts) != 3:
                await query.answer("❌ Ошибка формата данных", show_alert=True)
                return

            target_chat_id = int(parts[1])
            target_user_id = int(parts[2])

            print(f"🔍 DEBUG: target_chat_id={target_chat_id}, target_user_id={target_user_id}")

            # Проверяем, что кнопка нажата в том же чате
            if chat_id != target_chat_id:
                await query.answer("❌ Нельзя использовать эту кнопку в другом чате", show_alert=True)
                return

            # Ищем дуэль
            duel = self.duels.get(chat_id)
            if not duel:
                await query.answer("❌ Дуэль не найдена или завершена", show_alert=True)
                return

            print(f"🔍 DEBUG: Найдена дуэль, состояние: {duel['state']}")

            # Проверяем, что дуэль в процессе
            if duel["state"] != "in_progress":
                await query.answer("❌ Дуэль еще не началась или уже завершена", show_alert=True)
                return

            # Проверяем, что пользователь - участник дуэли
            if user_id not in [duel["creator_id"], duel["opponent_id"]]:
                await query.answer("❌ Только участники дуэли могут бросать кости", show_alert=True)
                return

            # Проверяем, что кнопка предназначена для этого пользователя
            if user_id != target_user_id:
                await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
                return

            # Проверяем через game структуру чей сейчас ход
            game = duel["game"]
            current_player = game["players"][game["current_index"]]

            if current_player["id"] != user_id:
                await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
                return

            print(f"🔍 DEBUG: Все проверки пройдены, бросаем кубик...")

            # Бросаем кубик
            dice_msg = await context.bot.send_dice(chat_id, emoji="🎲")
            value = dice_msg.dice.value

            print(f"🔍 DEBUG: Выпало значение: {value}")

            # Ждем анимацию
            await asyncio.sleep(3)

            # Обрабатываем бросок
            await self._process_duel_roll_with_game(duel, query, context, value, chat_id, user_id)

        except Exception as e:
            print(f"❌ Ошибка в duel_roll_handler: {e}")
            import traceback
            traceback.print_exc()
            await query.answer("❌ Ошибка при броске", show_alert=True)


    async def _process_simple_duel_roll(self, duel, query, context, value, chat_id, user_id):
        """Упрощенная обработка броска для дуэлей"""
        print(f"🔍 DEBUG _process_simple_duel_roll: user_id={user_id}, value={value}")

        # Инициализируем структуры если их нет
        if "rolls" not in duel:
            duel["rolls"] = {}
        if user_id not in duel["rolls"]:
            duel["rolls"][user_id] = []

        # Добавляем бросок
        duel["rolls"][user_id].append(value)

        # Определяем имена игроков
        player1_name = duel.get("creator_name", "Игрок 1")
        player2_name = duel.get("opponent_name", "Игрок 2")

        # Формируем статус
        rolls_p1 = duel["rolls"].get(duel["creator_id"], [])
        rolls_p2 = duel["rolls"].get(duel["opponent_id"], [])

        status = (
            f"🎲 Броски:\n"
            f"{player1_name}: {', '.join(map(str, rolls_p1)) or '—'}\n"
            f"{player2_name}: {', '.join(map(str, rolls_p2)) or '—'}\n\n"
            f"🎯 Текущий бросок: {value}"
        )

        # Проверяем завершение
        if len(rolls_p1) >= 3 and len(rolls_p2) >= 3:
            # Оба игрока завершили
            await self._finish_simple_duel(duel, context, chat_id)
        else:
            # Показываем кнопку для продолжения
            keyboard = [[InlineKeyboardButton("🎲 Бросить снова", callback_data="duel_roll:simple")]]
            await context.bot.send_message(chat_id, status, reply_markup=InlineKeyboardMarkup(keyboard))

    async def _process_duel_roll_with_game(self, duel, query, context, value, chat_id, user_id):
        """Обрабатывает бросок для дуэлей с структурой game"""
        print(f"🔍 DEBUG _process_duel_roll_with_game: user_id={user_id}, value={value}")

        game = duel["game"]

        # Записываем бросок
        game["rolls"][user_id].append(value)

        # Получаем имена игроков
        player1_name = duel.get("creator_name", "Игрок 1")
        player2_name = duel.get("opponent_name", "Игрок 2")

        # Формируем статус
        rolls_p1 = game["rolls"].get(duel["creator_id"], [])
        rolls_p2 = game["rolls"].get(duel["opponent_id"], [])

        current_player_name = player1_name if user_id == duel["creator_id"] else player2_name

        status = (
            f"🎲 {current_player_name} бросает кости!\n\n"
            f"📊 Текущие результаты:\n"
            f"{player1_name}: {', '.join(map(str, rolls_p1)) or '—'}\n"
            f"{player2_name}: {', '.join(map(str, rolls_p2)) or '—'}\n\n"
            f"🎯 Выпало: {value}"
        )

        # Проверяем, есть ли еще броски у текущего игрока
        current_rolls_count = len(game["rolls"][user_id])

        if current_rolls_count < 3:
            # Еще есть броски - показываем кнопку для этого же игрока
            status += f"\n\nБросок {current_rolls_count}/3"
            keyboard = [[InlineKeyboardButton("🎲 Бросить снова", callback_data=f"duel_roll:{chat_id}:{user_id}")]]
            await context.bot.send_message(chat_id, status, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # Игрок завершил все 3 броска
            status += f"\n\n✅ {current_player_name} завершил все броски!"

            # Передаем ход следующему игроку
            game["current_index"] += 1

            if game["current_index"] < len(game["players"]):
                next_player = game["players"][game["current_index"]]
                next_player_name = player1_name if next_player["id"] == duel["creator_id"] else player2_name

                status += f"\n\n➡️ Теперь ходит {next_player_name}"
                await context.bot.send_message(chat_id, status)

                # Показываем кнопку для следующего игрока
                await self.send_duel_roll_prompt(chat_id, next_player["id"])
            else:
                # Оба игрока завершили броски - завершаем дуэль
                await context.bot.send_message(chat_id, status + "\n\n⏳ Подсчитываем результаты...")
                await self._finish_duel_with_game(duel, context, chat_id)


    async def _process_duel_roll_active(self, duel, query, context, value, chat_id, player_id):
        """Обрабатывает бросок для активных дуэлей"""
        # Записываем бросок
        duel["rolls"].setdefault(player_id, []).append(value)

        # Смена хода
        duel["turn"] = duel["p2"] if player_id == duel["p1"] else duel["p1"]

        # Проверяем завершение
        p1_rolls = len(duel["rolls"].get(duel["p1"], []))
        p2_rolls = len(duel["rolls"].get(duel["p2"], []))

        if p1_rolls == 3 and p2_rolls == 3:
            await self.finish_duel(duel, context)
            if duel.get("msg_id"):
                del self.active_duels[duel["msg_id"]]
        else:
            # Показываем кнопку для следующего хода
            next_player_id = duel["turn"]
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎲 Бросить кубики",
                                     callback_data=f"duel_roll:{duel['msg_id']}")
            ]])

            status = f"🎲 Выпало: {value}\nХод переходит следующему игроку"
            await context.bot.send_message(chat_id, status, reply_markup=kb)

    async def _finish_duel_with_game(self, duel, context, chat_id):
        """Завершает дуэль с структурой game"""
        game = duel["game"]
        p1 = game["players"][0]
        p2 = game["players"][1]

        s1 = sum(game["rolls"][p1["id"]])
        s2 = sum(game["rolls"][p2["id"]])

        bet = duel["bet"]
        prize = bet * 2 * 0.92  # комиссия 8%

        if s1 > s2:
            winner_id = p1["id"]
            winner_name = p1["username"]
        elif s2 > s1:
            winner_id = p2["id"]
            winner_name = p2["username"]
        else:
            # Ничья
            self.db.update_balance(p1["id"], bet)
            self.db.update_balance(p2["id"], bet)
            await context.bot.send_message(
                chat_id,
                f"🤝 Ничья!\n{p1['username']}: {s1}\n{p2['username']}: {s2}\nСтавки возвращены."
            )
            return

        # Перевод победителю
        try:
            result = self.crypto_pay.transfer(
                user_id=winner_id,
                amount=prize,
                asset="USDT",
                spend_id=f"duelwin_{chat_id}_{winner_id}"
            )
            if not result.get("ok"):
                self.db.update_balance(winner_id, prize)
        except:
            self.db.update_balance(winner_id, prize)

        await context.bot.send_message(
            chat_id,
            f"🏆 Победитель: {winner_name}!\n\n"
            f"{p1['username']}: {s1}\n"
            f"{p2['username']}: {s2}\n\n"
            f"💰 Выигрыш: ${prize:.2f}"
        )


    async def duel_buttons_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        msg_id = query.message.message_id

        await query.answer()

        duel = self.active_duels.get(msg_id)
        if not duel:
            await query.edit_message_text("❌ Дуэль не найдена (возможно завершена)")
            return

        action = query.data

        # ───────── ОТМЕНА ─────────
        if action == "duel_cancel":
            if user_id != duel["p1"]:
                await query.answer("❌ Только создатель может отменить дуэль", show_alert=True)
                return

            await query.edit_message_text("❌ Дуэль отменена.")
            del self.active_duels[msg_id]
            return

        # ───────── ПРИНЯТИЕ ─────────
        if action == "duel_accept":
            if duel["p2"] is not None:
                await query.answer("❌ Дуэль уже принята!", show_alert=True)
                return

            if user_id == duel["p1"]:
                await query.answer("❌ Вы не можете принять свою дуэль", show_alert=True)
                return

            duel["p2"] = user_id
            duel["turn"] = duel["p1"]  # первым ходит p1

            await query.edit_message_text(
                f"⚔ Дуэль начинается!\n"
                f"🎲 Первый бросает <a href='tg://user?id={duel['p1']}'>игрок</a>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎲 Бросить кубики",
                                          callback_data=f"duel_roll:{msg_id}")]
                ])
            )
            return

        # ───────── БРОСОК ─────────
        if action.startswith("duel_roll"):
            if user_id != duel["turn"]:
                await query.answer("❌ Сейчас не ваш ход!", show_alert=True)
                return

            dice = await query.message.reply_dice("🎲")
            roll = dice.dice.value

            duel["rolls"].setdefault(user_id, []).append(roll)

            # смена хода
            duel["turn"] = duel["p2"] if user_id == duel["p1"] else duel["p1"]

            p1r = len(duel["rolls"].get(duel["p1"], []))
            p2r = len(duel["rolls"].get(duel["p2"], []))

            # оба сделали 3 броска — конец
            if p1r == 3 and p2r == 3:
                await self.finish_duel(duel, context)
                del self.active_duels[msg_id]
                return

            await query.message.reply_text(
                f"🎲 Выпало: <b>{roll}</b>\n"
                f"Теперь ход следующего игрока.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎲 Бросить кубики",
                                          callback_data=f"duel_roll:{msg_id}")]
                ])
            )

    async def finish_duel(self, duel, context):
        p1 = duel["p1"]
        p2 = duel["p2"]

        s1 = sum(duel["rolls"][p1])
        s2 = sum(duel["rolls"][p2])

        chat = duel["chat_id"]

        if s1 > s2:
            winner = p1
        elif s2 > s1:
            winner = p2
        else:
            winner = None

        if winner:
            await context.bot.send_message(
                chat,
                f"🏆 <a href='tg://user?id={winner}'>Победитель</a>!\n"
                f"🎲 Итог: <b>{s1}</b> vs <b>{s2}</b>",
                parse_mode="HTML"
            )
        else:
            await context.bot.send_message(
                chat,
                f"🤝 Ничья!\n"
                f"🎲 Счёт: <b>{s1}</b> vs <b>{s2}</b>",
                parse_mode="HTML"
            )

    # ======================  КОНЕЦ МОДУЛЯ ДУЭЛЕЙ  =======================

    async def show_deposit(self, query):
        keyboard = [
            [InlineKeyboardButton("$10", callback_data="deposit_10")],
            [InlineKeyboardButton("$25", callback_data="deposit_25")],
            [InlineKeyboardButton("$50", callback_data="deposit_50")],
            [InlineKeyboardButton("$100", callback_data="deposit_100")],
            [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "💳 Выберите сумму для пополнения:",
            reply_markup=reply_markup
        )

    async def show_withdraw(self, query):
        """Показываем варианты вывода"""
        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        if user:
            balance = user[4]
            keyboard = [
                [InlineKeyboardButton("$10", callback_data="withdraw_10")],
                [InlineKeyboardButton("$25", callback_data="withdraw_25")],
                [InlineKeyboardButton("$50", callback_data="withdraw_50")],
                [InlineKeyboardButton("$100", callback_data="withdraw_100")],
                [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_withdraw")],
                [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"💸 Вывод средств\n\n"
                f"💰 Доступно: ${balance:.0f}\n"
                "Выберите сумму для вывода:",
                reply_markup=reply_markup
            )

    async def process_deposit(self, query, amount):
        """Обрабатываем депозит через Crypto Pay"""
        user_id = query.from_user.id

        try:
            # Создаем счет для депозита
            invoice = self.crypto_pay.create_invoice(
                amount=amount,
                asset="USDT",
                description=f"Пополнение баланса на ${amount}"
            )

            if invoice.get('ok'):
                pay_url = invoice['result']['pay_url']
                invoice_id = invoice['result']['invoice_id']

                # Сохраняем в базу
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO crypto_transactions (user_id, invoice_id, amount, type, status)
                    VALUES (?, ?, ?, 'deposit', 'pending')
                ''', (user_id, invoice_id, amount))
                conn.commit()
                conn.close()

                await query.edit_message_text(
                    f"💳 Для пополнения на ${amount}:\n\n"
                    f"📎 Перейдите по ссылке:\n{pay_url}\n\n"
                    "После оплаты баланс обновится автоматически.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔗 Открыть ссылку", url=pay_url)],
                        [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                    ])
                )
            else:
                await query.edit_message_text("❌ Ошибка при создании счета")

        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {str(e)}")

    def check_duplicate_transaction(self, user_id, amount, transaction_type, time_window_minutes=5):
        """Проверяет, не было ли похожей транзакции недавно"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM crypto_transactions 
            WHERE user_id = ? AND amount = ? AND type = ? 
            AND created_at > datetime('now', ?)
        ''', (user_id, amount, transaction_type, f'-{time_window_minutes} minutes'))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

        except Exception as e:
            print(f"❌ DEBUG: Исключение в process_withdraw: {e}")
            await query.edit_message_text(
                f"❌ Ошибка при выводе: {str(e)}\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )

    async def ask_custom_deposit(self, query):
        """Запрашиваем произвольную сумму для депозита"""
        await query.edit_message_text(
            "💵 Введите сумму для пополнения (минимум $1):\n\n"
            "Пример: 15.5 или 75",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
            ])
        )


    async def ask_custom_withdraw(self, query):
        """Запрашиваем произвольную сумму для вывода"""
        await query.edit_message_text(
            "💵 Введите сумму для вывода:\n\n"
            "Пример: 15 или 75.5",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="withdraw")]
            ])
        )

    async def process_withdraw(self, query, amount):
        """Обрабатываем реальный вывод средств с проверкой дублирования"""
        print(f"🔍 DEBUG: process_withdraw вызван, сумма: {amount}")

        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        if not user:
            await query.edit_message_text("❌ Пользователь не найден")
            return

        balance = user[4]

        # Проверка дублирования
        if self.check_duplicate_transaction(user_id, amount, 'withdraw'):
            await query.edit_message_text(
                "⚠️ Похожая транзакция на вывод уже обрабатывается.\n"
                "Пожалуйста, подождите 5 минут или проверьте статус вывода.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                ])
            )
            return

        if balance < amount:
            await query.edit_message_text(
                f"❌ Недостаточно средств!\n"
                f"Ваш баланс: ${balance:.0f}\n"
                f"Запрошено: ${amount:.0f}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Пополнить", callback_data="deposit")],
                    [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                ])
            )
            return

        if amount < 1:
            await query.edit_message_text("❌ Минимальная сумма вывода $1")
            return

        try:
            # Генерируем уникальный spend_id
            import uuid
            spend_id = f"withdraw_{user_id}_{uuid.uuid4().hex[:8]}_{int(time.time())}"

            print(f"🔍 DEBUG: Выполняем вывод через Crypto Pay, spend_id: {spend_id}")
            transfer_result = self.crypto_pay.transfer(
                user_id=user_id,
                amount=amount,
                asset="USDT",
                spend_id=spend_id
            )

            print(f"🔍 DEBUG: Результат transfer: {transfer_result}")

            if transfer_result.get('ok'):
                # Обновляем баланс
                self.db.update_balance(user_id, -amount)

                # Сохраняем транзакцию с spend_id
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO crypto_transactions 
                    (user_id, amount, type, status, crypto_asset, invoice_id, spend_id)
                    VALUES (?, ?, 'withdraw', 'completed', 'USDT', ?, ?)
                ''', (user_id, amount, spend_id, spend_id))
                conn.commit()
                conn.close()

                new_balance = balance - amount
                await query.edit_message_text(
                    f"✅ Вывод ${amount:.0f} выполнен!\n\n"
                    f"💰 Новый баланс: ${new_balance:.0f}\n"
                    f"📋 ID транзакции: {spend_id}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                    ])
                )
            else:
                error_data = transfer_result.get('error', {})
                error_code = error_data.get('code')

                # Сохраняем FAILED транзакцию
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO crypto_transactions 
                    (user_id, amount, type, status, crypto_asset, error_message, spend_id)
                    VALUES (?, ?, 'withdraw', 'failed', 'USDT', ?, ?)
                ''', (user_id, amount, str(error_data), spend_id))
                conn.commit()
                conn.close()

                if error_code == 400 and 'INSUFFICIENT_FUNDS' in str(error_data):
                    error_message = (
                        "❌ Временно недоступно!\n\n"
                        "💰 На кошельке бота недостаточно средств для выплаты.\n\n"
                        "📞 Пожалуйста, обратитесь к администратору или попробуйте позже.\n"
                        "💳 Ваши средства остаются на вашем балансе."
                    )
                else:
                    error_message = f"❌ Ошибка вывода: {error_data}"

                await query.edit_message_text(
                    error_message,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                    ])
                )

        except Exception as e:
            print(f"❌ DEBUG: Исключение в process_withdraw: {e}")
            await query.edit_message_text(
                f"❌ Ошибка при выводе: {str(e)}\n\n"
                "Попробуйте позже или обратитесь в поддержку."
            )


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

    if not Config.BOT_TOKEN:
        logging.error("❌ BOT_TOKEN is missing in config!")
        return

    # Инициализируем основной объект бота
    bot = DiceGameBot()

    # Присваиваем глобальной переменной application чтобы webhook мог её использовать
    global application
    application = bot.application

    app_for_flask = app  # Flask экземпляр уже объявлен выше; не запускаем его автоматически here

    # --- Регистрация обработчиков сделана внутри bot.__init__ -> register_handlers()

    # Здесь запустим polling (удобно для разработки и Render)
    logging.info("🤖 Bot is starting via polling...")
    bot.application.run_polling()


if __name__ == "__main__":
    main()





