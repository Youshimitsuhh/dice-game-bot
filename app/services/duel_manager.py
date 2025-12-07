# app/services/duel_manager.py
import logging
from typing import Optional, Dict, Tuple, List
from datetime import datetime
import uuid

from ..models.duel import Duel


class DuelManager:
    """Менеджер дуэлей в групповых чатах"""

    def __init__(self, database):
        self.db = database
        self.active_duels: Dict[str, Duel] = {}  # duel_id -> Duel
        self.chat_duels: Dict[int, str] = {}  # chat_id -> duel_id (активная дуэль в чате)
        self.logger = logging.getLogger(__name__)

    def create_duel(self, chat_id: int, creator_id: int, creator_name: str,
                    bet_amount: float) -> Tuple[Optional[Duel], Optional[str]]:
        """Создает новую дуэль в чате"""
        try:
            # Проверяем, нет ли уже активной дуэли в чате
            if chat_id in self.chat_duels:
                active_duel = self.active_duels.get(self.chat_duels[chat_id])
                if active_duel and active_duel.status in ["waiting", "active"]:
                    return None, "В этом чате уже есть активная дуэль!"

            # Проверяем баланс создателя
            user = self.db.get_user(creator_id)
            if not user:
                return None, "Пользователь не найден"

            if user[4] < bet_amount:
                return None, f"Недостаточно средств. Баланс: ${user[4]:.0f}"

            # Резервируем средства
            self.db.update_balance(creator_id, -bet_amount)

            # Создаем дуэль
            duel_id = Duel.generate_duel_id()
            duel = Duel(
                duel_id=duel_id,
                chat_id=chat_id,
                creator_id=creator_id,
                creator_name=creator_name,
                bet_amount=bet_amount,
                status="waiting"
            )

            # Сохраняем
            self.active_duels[duel_id] = duel
            self.chat_duels[chat_id] = duel_id

            self.logger.info(f"Создана дуэль {duel_id} в чате {chat_id}")
            return duel, None

        except Exception as e:
            self.logger.error(f"Ошибка создания дуэли: {e}")
            return None, f"Ошибка создания дуэли: {str(e)}"

    def accept_duel(self, duel_id: str, opponent_id: int,
                    opponent_name: str) -> Tuple[Optional[Duel], Optional[str]]:
        """Принимает дуэль"""
        try:
            duel = self.active_duels.get(duel_id)
            if not duel:
                return None, "Дуэль не найдена"

            if duel.status != "waiting":
                return None, "Дуэль уже принята или отменена"

            if duel.creator_id == opponent_id:
                return None, "Нельзя принять собственную дуэль"

            # Проверяем баланс оппонента
            user = self.db.get_user(opponent_id)
            if not user:
                return None, "Пользователь не найден"

            if user[4] < duel.bet_amount:
                return None, f"Недостаточно средств. Нужно: ${duel.bet_amount:.0f}"

            # Резервируем средства оппонента
            self.db.update_balance(opponent_id, -duel.bet_amount)

            # Обновляем дуэль
            duel.opponent_id = opponent_id
            duel.opponent_name = opponent_name
            duel.status = "active"
            duel.started_at = datetime.now()

            self.logger.info(f"Дуэль {duel_id} принята игроком {opponent_name}")
            return duel, None

        except Exception as e:
            self.logger.error(f"Ошибка принятия дуэли: {e}")
            return None, f"Ошибка принятия дуэли: {str(e)}"

    def process_duel_roll(self, duel_id: str, player_id: int,
                          dice_value: int) -> Tuple[Optional[Duel], Optional[str]]:
        """Обрабатывает бросок в дуэли"""
        try:
            duel = self.active_duels.get(duel_id)
            if not duel:
                return None, "Дуэль не найдена"

            if duel.status != "active":
                return None, "Дуэль не активна"

            if not duel.is_player_in_duel(player_id):
                return None, "Вы не участник этой дуэли"

            # Добавляем бросок
            success = duel.add_roll(player_id, dice_value)
            if not success:
                return None, "Вы уже сделали все броски"

            # Проверяем завершение
            if duel.are_both_players_finished():
                duel.status = "finished"
                duel.finished_at = datetime.now()
                duel.winner_id = duel.calculate_winner()

                # TODO: Обработка выплат
                # self._process_duel_payout(duel)

            return duel, None

        except Exception as e:
            self.logger.error(f"Ошибка обработки броска в дуэли: {e}")
            return None, f"Ошибка броска: {str(e)}"

    def cancel_duel(self, duel_id: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """Отменяет дуэль"""
        try:
            duel = self.active_duels.get(duel_id)
            if not duel:
                return False, "Дуэль не найдена"

            if duel.status != "waiting":
                return False, "Нельзя отменить начавшуюся дуэль"

            if duel.creator_id != user_id:
                return False, "Только создатель может отменить дуэль"

            # Возвращаем средства создателю
            self.db.update_balance(user_id, duel.bet_amount)

            # Удаляем дуэль
            del self.active_duels[duel_id]
            if duel.chat_id in self.chat_duels:
                del self.chat_duels[duel.chat_id]

            self.logger.info(f"Дуэль {duel_id} отменена")
            return True, None

        except Exception as e:
            self.logger.error(f"Ошибка отмены дуэли: {e}")
            return False, f"Ошибка отмены: {str(e)}"

    def get_duel_by_chat(self, chat_id: int) -> Optional[Duel]:
        """Получает активную дуэль в чате"""
        duel_id = self.chat_duels.get(chat_id)
        if duel_id:
            return self.active_duels.get(duel_id)
        return None

    def get_duel_by_id(self, duel_id: str) -> Optional[Duel]:
        """Получает дуэль по ID"""
        return self.active_duels.get(duel_id)

    def _process_duel_payout(self, duel: Duel):
        """Обрабатывает выплаты по дуэли (заглушка)"""
        # TODO: Реализовать выплаты через crypto_pay
        pass

    def cleanup_old_duels(self, hours_old: int = 24):
        """Очищает старые дуэли"""
        try:
            now = datetime.now()
            to_remove = []

            for duel_id, duel in self.active_duels.items():
                if duel.created_at and (now - duel.created_at).total_seconds() > hours_old * 3600:
                    to_remove.append(duel_id)

                    # Возвращаем средства если дуэль была в ожидании
                    if duel.status == "waiting" and duel.creator_id:
                        self.db.update_balance(duel.creator_id, duel.bet_amount)

            for duel_id in to_remove:
                duel = self.active_duels.pop(duel_id, None)
                if duel and duel.chat_id in self.chat_duels:
                    del self.chat_duels[duel.chat_id]

            if to_remove:
                self.logger.info(f"Очищено {len(to_remove)} старых дуэлей")

        except Exception as e:
            self.logger.error(f"Ошибка очистки старых дуэлей: {e}")