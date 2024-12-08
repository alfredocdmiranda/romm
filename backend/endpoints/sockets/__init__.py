from joserfc import jwt

from config import LIBRARY_BASE_PATH, ROMM_AUTH_SECRET_KEY
from handler.auth.base_handler import ALGORITHM
from handler.database import db_user_handler
from handler.emulation_session_handler import emulation_session_handler
from handler.socket_handler import socket_handler
from handler.redis_handler import redis_client
from logger.logger import log

@socket_handler.socket_server.on("connect")
async def connect(sid, environ):
    """
    It clears the sessions
    """
    token = environ.get("HTTP_COOKIE")
    list_cookies = [cookie.split("=", 1) for cookie in token.split(";")]
    cookies = {key: value for key, value in list_cookies}
    access_token = cookies.get("romm_session")
    jwt_payload = jwt.decode(access_token, ROMM_AUTH_SECRET_KEY, ALGORITHM)
    username = jwt_payload.claims["sub"]
    redis_client.hmset(f"sid:{sid}", {"username": username})


@socket_handler.socket_server.on("disconnect")
async def disconnect(sid):
    """
    It clears the sessions
    """
    await emulation_session_handler.disconnect_active_session(sid)
    log.debug(f"Socket [{sid}] disconnected.")
    socket_handler.remove_sid(sid)