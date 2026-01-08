import logging
from typing import Optional, Dict, Tuple, List
from datetime import datetime
from ..models.game import PvPGame
import asyncio


class GameManager:
    """Менеджер игр 1 на 1"""

    def __init__(self, database, payment_manager=None):
        self.db = database
        self.payment_manager = payment_manager
        self.active_games: Dict[int, PvPGame] = {}
        self.game_messages: Dict[int, List[Dict[str, int]]] = {}
        self.logger = logging.getLogger(__name__)

    def create_game(self, creator_id: int, creator_name: str,
                    bet_amount: float) -> Tuple[Optional[PvPGame], Optional[str]]:
        """Создает новую игру 1 на 1"""
        try:
            # Проверяем баланс
            user = self.db.get_user(creator_id)
            if not user:
                return None, "Пользователь не найден"

            if user[4] < bet_amount:
                return None, f"Недостаточно средств. Баланс: ${user[4]:.0f}"

            # Создаем игру в БД (используем старый метод из database.py)
            game_id, game_code = self.db.create_game(creator_id, bet_amount)

            # Резервируем средства
            self.db.update_balance(creator_id, -bet_amount)

            # Создаем объект игры
            game = PvPGame(
                id=game_id,
                game_code=game_code,
                player1_id=creator_id,
                player1_name=creator_name,
                bet_amount=bet_amount,
                status="waiting"
            )

            # Сохраняем в активных играх
            self.active_games[game_id] = game

            self.logger.info(f"Создана игра {game_code} пользователем {creator_name}")
            return game, None

        except Exception as e:
            self.logger.error(f"Ошибка создания игры: {e}")
            return None, f"Ошибка создания игры: {str(e)}"

    def join_game(self, game_code: str, player_id: int,
                  player_name: str) -> Tuple[Optional[PvPGame], Optional[str]]:
        """Присоединяет второго игрока к игре"""
        try:
            # Ищем игру в БД
            game_data = self.db.get_game(game_code)
            if not game_data:
                return None, "Игра не найдена"

            game_id = game_data[0]

            # Проверяем, что игра еще не началась
            if game_data[16] is not None:  # p2_tg_id уже есть
                return None, "К игре уже присоединился второй игрок"

            # Проверяем баланс
            user = self.db.get_user(player_id)
            if not user:
                return None, "Пользователь не найден"

            if user[4] < game_data[3]:  # bet_amount
                return None, f"Недостаточно средств. Нужно: ${game_data[3]:.0f}"

            # Присоединяем в БД
            success, message = self.db.join_game(game_code, player_id)
            if not success:
                return None, message

            # Резервируем средства
            self.db.update_balance(player_id, -game_data[3])

            # Обновляем объект игры
            if game_id in self.active_games:
                game = self.active_games[game_id]
                game.player2_id = player_id
                game.player2_name = player_name
                game.status = "active"
            else:
                # Создаем объект из данных БД
                game = PvPGame(
                    id=game_id,
                    game_code=game_code,
                    player1_id=game_data[15],
                    player1_name=game_data[17] or "Игрок 1",
                    player2_id=player_id,
                    player2_name=player_name,
                    bet_amount=game_data[3],
                    status="active"
                )
                self.active_games[game_id] = game

            self.logger.info(f"Игрок {player_name} присоединился к игре {game_code}")
            return game, None

        except Exception as e:
            self.logger.error(f"Ошибка присоединения к игре: {e}")
            return None, f"Ошибка присоединения: {str(e)}"

    async def process_dice_roll(self, game_id: int, player_id: int,
                                dice_value: int) -> Tuple[Optional[PvPGame], Optional[str]]:
        """Обрабатывает бросок костей"""
        try:
            # Проверяем, что игра существует
            if game_id not in self.active_games:
                # Пробуем загрузить из БД
                game_data = self.db.get_game_by_id(game_id)
                if not game_data:
                    return None, "Игра не найдена"

                # Создаем объект из БД
                game = PvPGame(
                    id=game_id,
                    game_code=game_data[2],
                    player1_id=game_data[15],
                    player1_name=game_data[17] or "Игрок 1",
                    player2_id=game_data[16],
                    player2_name=game_data[18] or "Игрок 2",
                    bet_amount=game_data[3],
                    status=game_data[7]  # status из БД
                )
                self.active_games[game_id] = game

            game = self.active_games[game_id]

            # Проверяем, что игрок участвует в игре
            if player_id not in [game.player1_id, game.player2_id]:
                return None, "Вы не участвуете в этой игре"

            # Проверяем, что игра активна
            if game.status != "active":
                return None, "Игра не активна"

            # Добавляем бросок
            success = game.add_roll(player_id, dice_value)
            if not success:
                return None, "Вы уже сделали все броски"

            # Сохраняем в БД
            roll_data = self.db.save_dice_roll(game_id, player_id, dice_value)

            # Проверяем завершение
            if game.are_both_players_finished():
                game.status = "finished"
                game.winner_id = game.calculate_winner()

                # Сохраняем в БД
                self.db.finish_game(game_id, None)

                # Обрабатываем выплату победителю
                await self._process_game_payout(game)

                return game, None

            # ВАЖНО: Добавляем возврат если игра еще не завершена
            return game, None

        except Exception as e:
            self.logger.error(f"Ошибка обработки броска: {e}")
            return None, f"Ошибка броска: {str(e)}"


    async def _process_game_payout(self, game):
        """Обрабатывает выплаты по завершенной игре"""
        try:
            if not game.winner_id:
                self.logger.error(f"Нет победителя в игре {game.id}")
                return

            # Общий банк = 2 ставки
            total_bank = game.bet_amount * 2
            commission = total_bank * 0.08  # 8% комиссия
            winner_amount = total_bank - commission

            # Создаем выплату победителю через payment_manager
            if self.payment_manager:
                try:
                    payment, error = await self.payment_manager.create_withdrawal(
                        user_id=game.winner_id,
                        amount_usd=winner_amount,
                        description=f"Выигрыш в игре #{game.game_code}"
                    )

                    if payment:
                        self.logger.info(
                            f"✅ Выплата создана для игры {game.game_code}: {winner_amount:.2f}$ для пользователя {game.winner_id}")
                    else:
                        self.logger.error(f"❌ Ошибка создания выплаты для игры {game.game_code}: {error}")

                        # Если ошибка в payment_manager, хотя бы зачисляем на баланс
                        self.db.update_balance(game.winner_id, winner_amount)
                        self.logger.info(f"⚠️ Средства зачислены на баланс из-за ошибки платежа")
                except Exception as e:
                    self.logger.error(f"❌ Исключение в payment_manager: {e}")
                    # Запасной вариант: зачисляем на баланс
                    self.db.update_balance(game.winner_id, winner_amount)
            else:
                # Если нет payment_manager, просто обновляем баланс
                self.db.update_balance(game.winner_id, winner_amount)
                self.logger.info(f"⚠️ PaymentManager не доступен, баланс обновлен: +{winner_amount:.2f}$")

        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка в _process_game_payout: {e}")

    async def process_game_result(self, game, context, bot):
        """Обрабатывает результат завершенной игры с выплатой"""
        try:
            total_bank = game.bet_amount * 2
            commission = total_bank * 0.08  # 8%
            winner_amount = total_bank - commission

            winner_id = game.winner_id
            winner_name = game.player1_name if winner_id == game.player1_id else game.player2_name

            # 1. Уведомляем игроков
            winner_text = (
                f"🏆 Поздравляем с победой!\n"
                f"💰 Ваш выигрыш: ${winner_amount:.2f}\n"
                f"🎮 Противник: {game.player2_name if winner_id == game.player1_id else game.player1_name}"
            )

            loser_id = game.player2_id if winner_id == game.player1_id else game.player1_id
            loser_text = (
                f"😔 Вы проиграли\n"
                f"💰 Потеряно: ${game.bet_amount:.2f}\n"
                f"🎮 Победитель: {winner_name}"
            )

            await context.bot.send_message(chat_id=winner_id, text=winner_text)
            await context.bot.send_message(chat_id=loser_id, text=loser_text)

            # 2. Создаем чек победителю через payment_manager
            if hasattr(bot, 'payment_manager'):
                try:
                    # Создаем выплату победителю
                    payment, error = await bot.payment_manager.create_withdrawal(
                        user_id=winner_id,
                        amount_usd=winner_amount,
                        description=f"Выигрыш в игре #{game.id}"
                    )

                    if payment:
                        self.logger.info(
                            f"✅ Чек создан для победителя {winner_name}: ${winner_amount:.2f}")
                        await context.bot.send_message(
                            chat_id=winner_id,
                            text=f"💰 Чек на ${winner_amount:.2f} создан! Ожидайте выплаты."
                        )
                    else:
                        self.logger.error(f"❌ Ошибка создания чека: {error}")
                        await context.bot.send_message(
                            chat_id=winner_id,
                            text=f"⚠️ Ошибка выплаты: {error}"
                        )
                except Exception as e:
                    self.logger.error(f"❌ Ошибка payment_manager: {e}")

            # 3. Обновляем статистику в БД
            bot.db.update_balance(winner_id, winner_amount)

            self.logger.info(f"🎮 Игра {game.id} завершена. Победитель: {winner_name}")

        except Exception as e:
            self.logger.error(f"❌ Ошибка обработки результата: {e}")

    async def cancel_game(self, game_id: int, user_id: int, context=None) -> Tuple[bool, Optional[str]]:
        """Отменяет игру и возвращает средства"""
        try:
            # Проверяем, что игра существует
            game_data = self.db.get_game_by_id(game_id)
            if not game_data:
                return False, "Игра не найдена"

            # Проверяем права
            if game_data[15] != user_id:  # p1_tg_id
                return False, "Только создатель игры может её отменить"

            # Проверяем, что второй игрок не присоединился
            if game_data[16] is not None:
                return False, "Нельзя отменить игру с присоединившимся игроком"

            # Возвращаем средства
            bet_amount = game_data[3]
            self.db.update_balance(user_id, bet_amount)

            # Удаляем игру из БД
            self.db.cancel_game(game_id)

            # Удаляем только сохраненные сообщения (теперь их 2)
            if context and game_id in self.game_messages:
                self.logger.info(f"Удаляем сообщения игры {game_id}: {self.game_messages[game_id]}")

                for msg_data in self.game_messages[game_id]:
                    try:
                        await context.bot.delete_message(
                            chat_id=msg_data["chat_id"],
                            message_id=msg_data["message_id"]
                        )
                    except Exception as e:
                        if "Message to delete not found" not in str(e):
                            self.logger.warning(f"Не удалось удалить сообщение {msg_data}: {e}")

                del self.game_messages[game_id]

            # Удаляем из активных игр
            if game_id in self.active_games:
                del self.active_games[game_id]

            self.logger.info(f"Игра {game_id} отменена пользователем {user_id}")
            return True, None

        except Exception as e:
            self.logger.error(f"Ошибка отмены игры: {e}")
            return False, f"Ошибка отмены: {str(e)}"

    def get_game_by_code(self, game_code: str) -> Optional[PvPGame]:
        """Получает игру по коду"""
        # Пробуем найти в активных играх
        for game in self.active_games.values():
            if game.game_code == game_code:
                return game

        # Если не нашли, ищем в БД
        game_data = self.db.get_game(game_code)
        if game_data:
            game = PvPGame(
                id=game_data[0],
                game_code=game_data[2],
                player1_id=game_data[15],
                player1_name=game_data[17] or "Игрок 1",
                player2_id=game_data[16],
                player2_name=game_data[18] or "Игрок 2",
                bet_amount=game_data[3],
                status=game_data[7],
                player1_total=game_data[11] or 0,
                player2_total=game_data[12] or 0
            )
            self.active_games[game_data[0]] = game
            return game

        return None


