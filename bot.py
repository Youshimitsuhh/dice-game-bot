from telegram import MenuButtonCommands, BotCommand
import asyncio
import logging
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

    async def ask_custom_bet(self, query):
        """Запрашиваем произвольную сумму ставки"""
        await query.edit_message_text(
            "💵 Введите сумму ставки (минимум $1):\n\n"
            "Пример: 15 или 75.5",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад", callback_data="find_game")]
            ])
        )


    async def join_from_deeplink(self, update: Update, context: ContextTypes.DEFAULT_TYPE, game_code):
        """Обработка быстрого присоединения через deep link"""
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
        if context.args and context.args[0].startswith('join'):
            game_code = context.args[0][4:]  # Убираем 'join'
            await self.join_from_deeplink(update, context, game_code)
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

        if data == "find_game":
            await self.show_bet_options(query)
        elif data == "stats":
            await self.show_stats(query)
        elif data == "main_menu":
            await self.show_main_menu(query)
        elif data.startswith("bet_"):
            bet_amount = float(data.split("_")[1])
            await self.create_game(query, bet_amount)
        elif data.startswith("roll_"):
            game_id = int(data.split("_")[1])
            await self.roll_dice(query, game_id, context)
        elif data == "help":
            await self.show_help(query)
        elif data == "deposit":
            await self.show_deposit(query)
        elif data.startswith("deposit_"):
            amount = float(data.split("_")[1])
            await self.process_deposit(query, amount)
        elif data == "custom_bet":
            context.user_data['waiting_for_bet'] = True
            await self.ask_custom_bet(query)
        elif data == "withdraw":
            await self.show_withdraw(query)
        elif data.startswith("withdraw_"):
            amount = float(data.split("_")[1])
            await self.process_withdraw(query, amount)
        elif data == "custom_withdraw":
            context.user_data['waiting_for_withdraw'] = True
            await self.ask_custom_withdraw(query)
        elif data == "custom_deposit":
            context.user_data['waiting_for_deposit'] = True
            await self.ask_custom_deposit(query)
        elif data.startswith("copy_"):
            game_code = data.split("_")[1]
            await self.copy_command(query, game_code)

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
        user = query.from_user
        stats = self.db.get_user_stats(user.id)
        balance = stats[1] if stats else 0

        menu_text = (
            f"🎲 Главное меню\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            "Выберите действие:"
        )

        keyboard = [
            [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(menu_text, reply_markup=reply_markup)

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
        user_id = update.effective_user.id
        message_text = update.message.text

        print(f"🔍 DEBUG: handle_message получен текст: '{message_text}'")

        # Проверяем, ожидаем ли мы ввод суммы для СТАВКИ
        if context.user_data.get('waiting_for_bet'):
            context.user_data['waiting_for_bet'] = False  # Сбрасываем флаг
            try:
                bet_amount = float(message_text)
                if bet_amount < 1:
                    await update.message.reply_text("❌ Минимальная ставка $1")
                    return

                # Создаем игру с произвольной ставкой
                await self.create_game_from_message(update, bet_amount)

            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму (например: 25 или 50.5)")

        # Проверяем, ожидаем ли мы ввод суммы для ДЕПОЗИТА
        elif context.user_data.get('waiting_for_deposit'):
            context.user_data['waiting_for_deposit'] = False
            try:
                amount = float(message_text)
                if amount < 1:
                    await update.message.reply_text("❌ Минимальная сумма $1")
                    return

                # Создаем счет для депозита
                invoice = self.crypto_pay.create_invoice(
                    amount=amount,
                    asset="USDT",
                    description=f"Пополнение баланса на ${amount}"
                )

                if invoice.get('ok'):
                    pay_url = invoice['result']['pay_url']
                    invoice_id = invoice['result']['invoice_id']

                    # Сохраняем в базу (Crypto Pay ID пока не известен)
                    conn = self.db.get_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO crypto_transactions (user_id, invoice_id, amount, type, status)
                        VALUES (?, ?, ?, 'deposit', 'pending')
                    ''', (user_id, invoice_id, amount))
                    conn.commit()
                    conn.close()

                    await update.message.reply_text(
                        f"💳 Для пополнения на ${amount}:\n\n"
                        f"📎 Перейдите по ссылке:\n{pay_url}\n\n"
                        "После оплаты баланс обновится автоматически.\n"
                        "💰 Первый депозит автоматически привяжет ваш кошелек!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔗 Открыть ссылку", url=pay_url)],
                            [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                        ])
                    )
                else:
                    await update.message.reply_text("❌ Ошибка при создании счета")

            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму")

        # Проверяем, ожидаем ли мы ввод суммы для ВЫВОДА
        elif context.user_data.get('waiting_for_withdraw'):
            context.user_data['waiting_for_withdraw'] = False
            try:
                amount = float(message_text)
                await self.process_withdraw_from_message(update, amount)
            except ValueError:
                await update.message.reply_text("❌ Введите корректную сумму")

        else:
            # ЕСЛИ сообщение - число, но контекст не установлен
            try:
                number = float(message_text)
                await update.message.reply_text(
                    "💡 Вы ввели число, но не выбрали действие.\n\n"
                    "Используйте меню для:\n"
                    "• Создания игры\n• Пополнения баланса\n• Вывода средств"
                )
            except ValueError:
                # Если не число - открываем меню
                await self.menu_command(update, context)

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
        try:
            amount = float(context.args[0])
            user_id = update.effective_user.id
            self.db.update_balance(user_id, amount)
            await update.message.reply_text(f"✅ Баланс пополнен на {amount}")
        except (IndexError, ValueError):
            await update.message.reply_text("Использование: /deposit [сумма]")

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
        keyboard = [[InlineKeyboardButton("🎲 Бросить кости", callback_data=f"roll_{game_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Сообщение для создателя игры С КНОПКОЙ
        await query.edit_message_text(
            f"🎲 Игра создана!\n"
            f"💰 Ставка: ${bet_amount:.0f}\n\n"
            f"🆔 Код игры: `{game_code}`\n\n"
            "📤 **Перешли другу сообщение ниже:**\n\n"
            "🎲 Готовы бросить кости?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Второе сообщение - команда для пересылки
        await query.message.reply_text(
            f"`/join {game_code}`",
            parse_mode='Markdown'
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
        self.db.register_user(user.id, user.username, user.first_name)

        # Получаем статистику для показа в меню
        stats = self.db.get_user_stats(user.id)
        balance = stats[1] if stats else 0

        menu_text = (
            f"🎲 Главное меню\n\n"
            f"💰 Баланс: ${balance:.0f}\n"
            "Выберите действие:"
        )

        keyboard = [
            [InlineKeyboardButton("🎯 Создать игру", callback_data="find_game")],
            [InlineKeyboardButton("📊 Моя статистика", callback_data="stats")],
            [InlineKeyboardButton("💳 Пополнить баланс", callback_data="deposit"),
             InlineKeyboardButton("💸 Вывести средства", callback_data="withdraw")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(menu_text, reply_markup=reply_markup)


    async def show_deposit(self, query):
        keyboard = [
            [InlineKeyboardButton("$10", callback_data="deposit_10")],
            [InlineKeyboardButton("$25", callback_data="deposit_25")],
            [InlineKeyboardButton("$50", callback_data="deposit_50")],
            [InlineKeyboardButton("$100", callback_data="deposit_100")],
            [InlineKeyboardButton("💵 Произвольная сумма", callback_data="custom_deposit")],  # ← ЭТА КНОПКА
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
        """Обрабатываем реальный вывод средств через Crypto Pay"""
        print(f"🔍 DEBUG: process_withdraw вызван, сумма: {amount}")

        user_id = query.from_user.id
        user = self.db.get_user(user_id)

        if not user:
            await query.edit_message_text("❌ Пользователь не найден")
            return

        balance = user[4]

        if balance < amount:
            # ... существующий код для недостатка средств у пользователя ...
            return

        if amount < 1:
            await query.edit_message_text("❌ Минимальная сумма вывода $1")
            return

        try:
            print(f"🔍 DEBUG: Пытаемся выполнить вывод через Crypto Pay...")
            transfer_result = self.crypto_pay.transfer(
                user_id=user_id,
                amount=amount,
                asset="USDT",
                spend_id=f"withdraw_{user_id}_{amount}"
            )

            print(f"🔍 DEBUG: Результат transfer: {transfer_result}")

        except Exception as e:
            print(f"❌ Ошибка при выводе: {e}")
            await query.edit_message_text("❌ Ошибка при обработке вывода")
            return

        try:
            if transfer_result.get('ok'):
                # КОД УСПЕШНОГО ВЫВОДА
                print("✅ Вывод успешно выполнен")
                # TODO: Добавьте логику успешного вывода (обновление баланса и т.д.)
                await query.edit_message_text(
                    "✅ Вывод успешно выполнен!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Меню", callback_data="main_menu")]
                    ])
                )
            else:
                error_data = transfer_result.get('error', {})
                error_code = error_data.get('code')

                if error_code == 400 and 'INSUFFICIENT_FUNDS' in str(error_data):
                    # УЛУЧШЕННОЕ СООБЩЕНИЕ ДЛЯ НЕДОСТАТКА СРЕДСТВ НА КОШЕЛЬКЕ БОТА
                    error_message = (
                        "❌ Временно недоступно!\n\n"
                        "💰 На кошельке бота недостаточно средств для выплаты.\n\n"
                        "📞 Пожалуйста, обратитесь к администратору:\n"
                        "• Для пополнения кошелька бота\n"
                        "• Или попробуйте позже\n\n"
                        "💳 Ваши средства в безопасности и остаются на вашем балансе."
                    )
                else:
                    error_message = f"❌ Ошибка вывода: {error_data}\n\nПопробуйте позже или обратитесь в поддержку."

                print(f"❌ DEBUG: Ошибка вывода: {error_data}")
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
                "Попробуйте позже."
            )


def main():
    bot = DiceGameBot()
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # СНАЧАЛА команды
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("join", bot.join_command))
    application.add_handler(CommandHandler("menu", bot.menu_command))
    application.add_handler(CommandHandler("deposit", bot.deposit_command))

    # Обработчик для "/join КОД" как текстового сообщения
    async def handle_join_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        if text.startswith('/join'):
            context.args = text.split()[1:]
            await bot.join_command(update, context)

    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r'^/join\s+\w+'), handle_join_text))

    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(bot.button_handler))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT, bot.handle_message))

    # Дебаг-обработчик для ВСЕХ сообщений (последним)
    async def debug_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message and not update.message.text.startswith('/join'):
            print(f"🔍 DEBUG: Сообщение получено: '{update.message.text}'")

    application.add_handler(MessageHandler(filters.ALL, debug_all))

    print("🔍 DEBUG: Запускаем бота...")
    application.run_polling()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    if not Config.BOT_TOKEN:
        logging.error("BOT_TOKEN not configured!")
        exit(1)


    port = int(os.getenv('PORT', 5000))
    logging.info(f"Starting bot on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)



