# app/models/lobby.py
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import json


@dataclass
class LobbyPlayer:
    """Игрок в лобби"""
    id: int
    username: str
    ready: bool = False
    paid: bool = False
    last_roll: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'username': self.username,
            'ready': self.ready,
            'paid': self.paid,
            'last_roll': self.last_roll
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'LobbyPlayer':
        return cls(
            id=data['id'],
            username=data['username'],
            ready=data.get('ready', False),
            paid=data.get('paid', False),
            last_roll=data.get('last_roll')
        )


@dataclass
class Lobby:
    """Модель лобби"""
    id: str
    creator_id: int
    creator_name: str
    max_players: int
    bet_amount: float = 0.0
    players: List[LobbyPlayer] = field(default_factory=list)
    status: str = "waiting"  # waiting, active, finished
    timer_started: bool = False
    timer_expires_at: Optional[float] = None
    message_chat_id: Optional[int] = None
    message_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)

    def add_player(self, player: LobbyPlayer) -> bool:
        """Добавляет игрока в лобби"""
        if len(self.players) >= self.max_players:
            return False
        if any(p.id == player.id for p in self.players):
            return False
        self.players.append(player)
        return True

    def remove_player(self, user_id: int) -> bool:
        """Удаляет игрока из лобби"""
        initial_count = len(self.players)
        self.players = [p for p in self.players if p.id != user_id]
        return len(self.players) != initial_count

    def get_player(self, user_id: int) -> Optional[LobbyPlayer]:
        """Получает игрока по ID"""
        for player in self.players:
            if player.id == user_id:
                return player
        return None

    def toggle_player_ready(self, user_id: int) -> bool:
        """Переключает статус готовности игрока"""
        player = self.get_player(user_id)
        if player:
            player.ready = not player.ready
            return True
        return False

    def all_players_ready(self) -> bool:
        """Все ли игроки готовы?"""
        if len(self.players) < self.max_players:
            return False
        return all(p.ready for p in self.players)

    def get_player_count(self) -> int:
        """Количество игроков в лобби"""
        return len(self.players)

    def is_full(self) -> bool:
        """Заполнено ли лобби?"""
        return len(self.players) >= self.max_players

    def to_dict(self) -> Dict:
        """Конвертирует лобби в словарь для сохранения"""
        return {
            'id': self.id,
            'creator_id': self.creator_id,
            'creator_name': self.creator_name,
            'max_players': self.max_players,
            'bet_amount': self.bet_amount,
            'players': [p.to_dict() for p in self.players],
            'status': self.status,
            'timer_started': self.timer_started,
            'timer_expires_at': self.timer_expires_at,
            'message_chat_id': self.message_chat_id,
            'message_id': self.message_id,
            'created_at': self.created_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Lobby':
        """Создает лобби из словаря"""
        players_data = data.get('players', [])
        players = [LobbyPlayer.from_dict(p) for p in players_data]

        return cls(
            id=data['id'],
            creator_id=data['creator_id'],
            creator_name=data['creator_name'],
            max_players=data['max_players'],
            bet_amount=data.get('bet_amount', 0.0),
            players=players,
            status=data.get('status', 'waiting'),
            timer_started=data.get('timer_started', False),
            timer_expires_at=data.get('timer_expires_at'),
            message_chat_id=data.get('message_chat_id'),
            message_id=data.get('message_id'),
            created_at=data.get('created_at', time.time())
        )

    def get_lobby_text(self) -> str:
        """Формирует текст сообщения лобби"""
        players_text = "\n".join(
            f"{p.username} — {'✅' if p.ready else '❌'}"
            for p in self.players
        )

        timer_info = ""
        if self.timer_started and self.timer_expires_at:
            time_left = max(0, int(self.timer_expires_at - time.time()))
            if time_left > 0:
                timer_info = f"\n\n⏳ Таймер: {time_left} сек"

        bet_info = ""
        if self.bet_amount > 0:
            bet_info = f"💰 Ставка: ${self.bet_amount:.0f} с игрока\n"
            total_bank = self.bet_amount * self.max_players
            bet_info += f"🏦 Общий банк: ${total_bank:.0f}\n"

        return (
            f"🎲 Лобби #{self.id}\n"
            f"{bet_info}"
            f"👤 Владелец: {self.creator_name}\n"
            f"👥 Игроки ({len(self.players)}/{self.max_players}):\n{players_text}"
            f"{timer_info}"
        )