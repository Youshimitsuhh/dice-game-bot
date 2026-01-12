# app/services/lobby_manager.py
import uuid
import json
import asyncio
import logging
import time
from typing import Dict, Optional

from app.models.lobby import Lobby, LobbyPlayer

logger = logging.getLogger(__name__)


class LobbyManager:
    """Менеджер для управления лобби"""

    def __init__(self, db):
        self.db = db
        self.lobbies: Dict[str, Lobby] = {}  # lobby_id -> Lobby object
        logger.info("🔄 Менеджер лобби инициализирован")

    def create_lobby(self, creator_id: int, creator_name: str,
                     bet_amount: float, max_players: int) -> Lobby:
        """Создает новое лобби"""
        lobby_id = self._generate_lobby_id()

        # Создаем лобби
        lobby = Lobby(
            id=lobby_id,
            creator_id=creator_id,
            creator_name=creator_name,
            max_players=max_players,
            bet_amount=bet_amount
        )

        # Добавляем создателя как игрока
        creator_player = LobbyPlayer(
            id=creator_id,
            username=creator_name,
            paid=True  # Создатель уже оплатил
        )
        lobby.add_player(creator_player)

        # Сохраняем
        self.lobbies[lobby_id] = lobby
        logger.info(f"🎲 Создано лобби {lobby_id} для {creator_name}")

        return lobby

    def get_lobby(self, lobby_id: str) -> Optional[Lobby]:
        """Получает лобби по ID"""
        return self.lobbies.get(lobby_id)

    def join_lobby(self, lobby_id: str, user_id: int, username: str) -> tuple[bool, str]:
        """Присоединяет игрока к лобби"""
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return False, "Лобби не найдено"

        if lobby.is_full():
            return False, "Лобби заполнено"

        if lobby.get_player(user_id):
            return False, "Вы уже в этом лобби"

        # Создаем игрока
        player = LobbyPlayer(
            id=user_id,
            username=username,
            paid=False  # Пока не оплатил
        )

        if lobby.add_player(player):
            logger.info(f"👤 Игрок {username} присоединился к лобби {lobby_id}")
            return True, "Вы присоединились к лобби"

        return False, "Ошибка присоединения"

    def leave_lobby(self, lobby_id: str, user_id: int) -> tuple[bool, str]:
        """Игрок выходит из лобби"""
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return False, "Лобби не найдено"

        if not lobby.get_player(user_id):
            return False, "Вы не в этом лобби"

        # Удаляем игрока
        lobby.remove_player(user_id)
        logger.info(f"👤 Игрок {user_id} вышел из лобби {lobby_id}")

        # Если лобби пустое - удаляем его
        if not lobby.players:
            self.delete_lobby(lobby_id)
            return True, "Лобби удалено (пустое)"

        # Если вышел создатель - назначаем нового
        if user_id == lobby.creator_id and lobby.players:
            new_creator = lobby.players[0]
            lobby.creator_id = new_creator.id
            lobby.creator_name = new_creator.username
            logger.info(f"👑 Новый владелец лобби {lobby_id}: {new_creator.username}")

        return True, "Вы вышли из лобби"

    def toggle_ready(self, lobby_id: str, user_id: int) -> tuple[bool, str]:
        """Переключает статус готовности игрока"""
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return False, "Лобби не найдено"

        player = lobby.get_player(user_id)
        if not player:
            return False, "Вы не в этом лобби"

        player.ready = not player.ready
        status = "готов" if player.ready else "не готов"
        logger.info(f"✅ Игрок {player.username} теперь {status}")

        return True, f"Вы теперь {status}"

    def delete_lobby(self, lobby_id: str):
        """Удаляет лобби"""
        if lobby_id in self.lobbies:
            del self.lobbies[lobby_id]
            logger.info(f"🗑 Удалено лобби {lobby_id}")

    def _generate_lobby_id(self) -> str:
        """Генерирует уникальный ID для лобби"""
        return uuid.uuid4().hex[:8].upper()

    async def start_lobby_timer(self, lobby_id: str, callback_func, timeout: int = 30):
        """Запускает таймер для лобби"""
        lobby = self.get_lobby(lobby_id)
        if not lobby:
            return

        lobby.timer_started = True
        lobby.timer_expires_at = time.time() + timeout  # ← Использует time

        logger.info(f"⏰ Запущен таймер для лобби {lobby_id} ({timeout} сек)")

        try:
            await asyncio.sleep(timeout)

            # Проверяем, что лобби еще существует
            lobby = self.get_lobby(lobby_id)
            if lobby and lobby.all_players_ready():
                await callback_func(lobby_id)
            elif lobby:
                # Сбрасываем таймер если не все готовы
                lobby.timer_started = False
                lobby.timer_expires_at = None

        except Exception as e:
            logger.error(f"❌ Ошибка таймера лобби {lobby_id}: {e}")

    def get_active_lobbies(self) -> Dict[str, Lobby]:
        """Получает все активные лобби"""
        return {lid: lobby for lid, lobby in self.lobbies.items()
                if lobby.status == "waiting"}

    def save_lobby_to_db(self, lobby: Lobby):
        """Сохраняет лобби в базу данных"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()

            # Преобразуем игроков в JSON
            players_json = json.dumps([p.to_dict() for p in lobby.players])

            # Проверяем существует ли лобби в БД
            cursor.execute("SELECT id FROM lobbies WHERE id = ?", (lobby.id,))
            exists = cursor.fetchone()

            if exists:
                # Обновляем существующее
                cursor.execute('''
                    UPDATE lobbies 
                    SET creator_id = ?, creator_name = ?, max_players = ?, 
                        bet_amount = ?, players = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (
                    lobby.creator_id,
                    lobby.creator_name,
                    lobby.max_players,
                    lobby.bet_amount,
                    players_json,
                    lobby.status,
                    lobby.id
                ))
            else:
                # Вставляем новое
                cursor.execute('''
                    INSERT INTO lobbies 
                    (id, creator_id, creator_name, max_players, bet_amount, players, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    lobby.id,
                    lobby.creator_id,
                    lobby.creator_name,
                    lobby.max_players,
                    lobby.bet_amount,
                    players_json,
                    lobby.status
                ))

            conn.commit()
            conn.close()
            logger.debug(f"💾 Лобби {lobby.id} сохранено в БД")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка сохранения лобби {lobby.id}: {e}")
            return False

    def cleanup_old_lobbies(self, timeout_minutes=5):
        """Удаляет лобби старше указанного времени (по умолчанию 5 минут)"""
        # Убираем import time - он уже в начале файла

        current_time = time.time()
        timeout_seconds = timeout_minutes * 60

        lobbies_to_remove = []

        for lobby_id, lobby in list(self.lobbies.items()):
            # Пропускаем активные игры
            if lobby.status == "active":
                continue

            lobby_age = current_time - lobby.created_at

            # Условия для удаления:
            # 1. Лобби старше timeout_minutes минут
            # 2. И мало игроков (<= 1) или пустое
            if lobby_age > timeout_seconds:
                if len(lobby.players) <= 1:  # Только создатель или пусто
                    lobbies_to_remove.append((lobby_id, lobby))

        # Удаляем лобби
        for lobby_id, lobby in lobbies_to_remove:
            # Возвращаем ставку создателю если он один и оплатил
            if len(lobby.players) == 1:
                creator = lobby.players[0]
                if creator.paid and lobby.bet_amount > 0:
                    try:
                        self.db.update_balance(creator.id, lobby.bet_amount)
                        logger.info(
                            f"💰 Возвращена ставка ${lobby.bet_amount:.0f} создателю {creator.username} (ID: {creator.id})")
                    except Exception as e:
                        logger.error(f"❌ Ошибка возврата ставки создателю {creator.id}: {e}")

            # Удаляем из памяти
            del self.lobbies[lobby_id]

            # Удаляем из БД
            try:
                conn = self.db.get_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM lobbies WHERE id = ?", (lobby_id,))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"❌ Ошибка удаления лобби {lobby_id} из БД: {e}")

            age_minutes = lobby_age // 60
            logger.info(
                f"🗑️ Удалено старое лобби {lobby_id} (возраст: {age_minutes:.0f} мин, игроков: {len(lobby.players)})")

        return len(lobbies_to_remove)

    def get_all_lobbies(self):
        """Получает все лобби (для очистки)"""
        return list(self.lobbies.values())