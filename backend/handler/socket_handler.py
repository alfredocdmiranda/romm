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
    
    def get_sid_username(self, sid: str):
        return redis_client.hget(f"sid:{sid}", "username")
    
    def remove_sid(self, sid: str):
        redis_client.delete(f"sid:{sid}")


socket_handler = SocketHandler()
