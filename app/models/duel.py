from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict
import random


@dataclass
class Duel:
    """Модель дуэли в групповом чате"""
    duel_id: str
    chat_id: int
    creator_id: int
    creator_name: str
    opponent_id: Optional[int] = None
    opponent_name: Optional[str] = None
    bet_amount: float = 0.0
    status: str = "waiting"  # waiting, active, finished, cancelled
    creator_rolls: List[int] = None
    opponent_rolls: List[int] = None
    creator_total: int = 0
    opponent_total: int = 0
    winner_id: Optional[int] = None
    message_id: Optional[int] = None  # ID сообщения с дуэлью в чате
    created_at: datetime = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def __post_init__(self):
        if self.creator_rolls is None:
            self.creator_rolls = []
        if self.opponent_rolls is None:
            self.opponent_rolls = []
        if self.created_at is None:
            self.created_at = datetime.now()

    def add_roll(self, player_id: int, dice_value: int) -> bool:
        """Добавляет бросок игроку"""
        if player_id == self.creator_id:
            if len(self.creator_rolls) >= 3:
                return False
            self.creator_rolls.append(dice_value)
            self.creator_total = sum(self.creator_rolls)
            return True
        elif player_id == self.opponent_id:
            if len(self.opponent_rolls) >= 3:
                return False
            self.opponent_rolls.append(dice_value)
            self.opponent_total = sum(self.opponent_rolls)
            return True
        return False

    def is_player_finished(self, player_id: int) -> bool:
        """Проверяет, завершил ли игрок все броски"""
        if player_id == self.creator_id:
            return len(self.creator_rolls) >= 3
        elif player_id == self.opponent_id:
            return len(self.opponent_rolls) >= 3
        return False

    def are_both_players_finished(self) -> bool:
        """Проверяет, завершили ли оба игрока броски"""
        return (len(self.creator_rolls) >= 3 and
                len(self.opponent_rolls) >= 3)

    def calculate_winner(self) -> Optional[int]:
        """Определяет победителя"""
        if not self.are_both_players_finished():
            return None

        if self.creator_total > self.opponent_total:
            return self.creator_id
        elif self.opponent_total > self.creator_total:
            return self.opponent_id
        else:
            return None  # Ничья

    def is_player_in_duel(self, user_id: int) -> bool:
        """Проверяет, участвует ли пользователь в дуэли"""
        return user_id in [self.creator_id, self.opponent_id]

    def get_opponent_id(self, user_id: int) -> Optional[int]:
        """Получает ID оппонента"""
        if user_id == self.creator_id:
            return self.opponent_id
        elif user_id == self.opponent_id:
            return self.creator_id
        return None

    def get_player_name(self, user_id: int) -> Optional[str]:
        """Получает имя игрока по ID"""
        if user_id == self.creator_id:
            return self.creator_name
        elif user_id == self.opponent_id:
            return self.opponent_name
        return None

    @staticmethod
    def generate_duel_id() -> str:
        """Генерирует ID дуэли (8 символов)"""
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))