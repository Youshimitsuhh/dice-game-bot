from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
import random
import string


@dataclass
class PvPGame:
    """Модель игры 1 на 1"""
    id: int
    game_code: str
    player1_id: int
    player1_name: str
    player2_id: Optional[int] = None
    player2_name: Optional[str] = None
    bet_amount: float = 0.0
    status: str = "waiting"  # waiting, active, finished, cancelled
    player1_rolls: List[int] = None
    player2_rolls: List[int] = None
    player1_total: int = 0
    player2_total: int = 0
    winner_id: Optional[int] = None
    created_at: datetime = None

    def __post_init__(self):
        if self.player1_rolls is None:
            self.player1_rolls = []
        if self.player2_rolls is None:
            self.player2_rolls = []
        if self.created_at is None:
            self.created_at = datetime.now()

    def add_roll(self, player_id: int, dice_value: int) -> bool:
        """Добавляет бросок игроку"""
        if player_id == self.player1_id:
            if len(self.player1_rolls) >= 3:
                return False
            self.player1_rolls.append(dice_value)
            self.player1_total = sum(self.player1_rolls)
            return True
        elif player_id == self.player2_id:
            if len(self.player2_rolls) >= 3:
                return False
            self.player2_rolls.append(dice_value)
            self.player2_total = sum(self.player2_rolls)
            return True
        return False

    def is_player_finished(self, player_id: int) -> bool:
        """Проверяет, завершил ли игрок все броски"""
        if player_id == self.player1_id:
            return len(self.player1_rolls) >= 3
        elif player_id == self.player2_id:
            return len(self.player2_rolls) >= 3
        return False

    def are_both_players_finished(self) -> bool:
        """Проверяет, завершили ли оба игрока броски"""
        return (len(self.player1_rolls) >= 3 and
                len(self.player2_rolls) >= 3)

    def calculate_winner(self) -> Optional[int]:
        """Определяет победителя"""
        if not self.are_both_players_finished():
            return None

        if self.player1_total > self.player2_total:
            return self.player1_id
        elif self.player2_total > self.player1_total:
            return self.player2_id
        else:
            return None  # Ничья

    @staticmethod
    def generate_game_code() -> str:
        """Генерирует код игры (6 символов)"""
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


