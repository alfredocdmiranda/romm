import socketio  # type: ignore

from config import REDIS_URL
from handler.redis_handler import redis_client
from logger.logger import log


class SocketHandler:
    def __init__(self) -> None:
        self.socket_server = socketio.AsyncServer(
            cors_allowed_origins="*",
            async_mode="asgi",
            logger=False,
            engineio_logger=False,
            client_manager=socketio.AsyncRedisManager(str(REDIS_URL)),
        )

        self.socket_app = socketio.ASGIApp(
            self.socket_server, socketio_path="/ws/socket.io"
        )

        self._socker_users_ids: dict[str, int] = {}
    
    def add_connection(self, sid: str, user_id: int):
        self._socker_users_ids[sid] = user_id
        redis_client.set(f"sid:{sid}", user_id)
    
    def remove_connection(self, sid: str):
        del self._socker_users_ids[sid]
        redis_client.delete(f"sid:{sid}")
    
    def get_user_id(self, sid: str) -> int | None:
        user_id = redis_client.get(f"sid:{sid}")
        return int(user_id) if user_id else None


socket_handler = SocketHandler()
