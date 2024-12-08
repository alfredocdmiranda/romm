import asyncio
from collections import defaultdict
import socket
import struct
import subprocess
import uuid
from enum import Enum
from logger.logger import log
from pathlib import Path

from config import LIBRARY_BASE_PATH
from handler.redis_handler import redis_client
from handler.socket_handler import socket_handler
from models.rom import Rom

RETRO_SERVER_BIN = "/bin/retro_server"
LIBRETRO_PATH = "/romm/libretro"

# This is harded coded for tests
MAPPING_CORES = {
    "snes": "snes9x_libretro.so",
    # "n64": "mupen64plus_next_libretro.so",  # TODO Still need to make it work in retro-server
}

SOCKETS_MAPPING = {}


class EmulatorCommands(Enum):
    AUDIO = 1
    VIDEO = 2
    CONFIG = 3


class EmulationSessionHandler:
    def __init__(self, port_range):
        self._port_range = port_range
    
    def list_sessions_by_user(self, username: str):
        log.warning(f"GETTING: sessions:user:{username}")
        session_keys = redis_client.smembers(f"sessions:user:{username}")
        session_keys = [f"session:{session_id}" for session_id in session_keys]
        log.warning(f"KEYS: {session_keys}")
        with redis_client.pipeline() as pipe:
            for key in session_keys:
                pipe.hgetall(key)
            sessions = pipe.execute()
        
        return sessions
    
    def get_session_by_id(self, session_id: str):
        key = f"session:{session_id}"
        session = redis_client.hgetall(key)
        return session

    def get_active_session(self, sid: str) -> str:
        return redis_client.hget(f"sid:{sid}", "session_id")

    def get_avaliable_port(self):
        for i in self._port_range:
            if not redis_client.sismember("sessions:ports", i):
                redis_client.sadd("sessions:ports", i)
                return i
    
    def release_port(self, port):
        redis_client.srem("sessions:ports", port)
    
    async def create_session(self, sid, rom: Rom):
        try:
            rs_proc = None

            rom_fullpath = Path(LIBRARY_BASE_PATH, rom.full_path)
            libretro_core = Path(LIBRETRO_PATH, MAPPING_CORES[rom.platform.slug])
            
            port = self.get_avaliable_port()
            if port is None:
                raise ValueError("No Port is Available")
            
            log.info(f"{libretro_core} {rom_fullpath} {port}")
            f = open(f"/{sid}.log", "w")
            rs_proc = subprocess.Popen([RETRO_SERVER_BIN, "-p", str(port), libretro_core, rom_fullpath], start_new_session=True, stdout=None, stderr=None)
            await asyncio.sleep(1)
        except BaseException as err:
            log.exception(f"Some Error: {err}")
            if rs_proc is not None:
                rs_proc.kill()
        else:
            session = {
                "id": str(uuid.uuid4()),
                "rom": rom.name or rom.file_name_no_ext,
                "core": MAPPING_CORES[rom.platform.slug],
                "platform": rom.platform.slug,
                "players": 0,
                "port": port,
                "pid": rs_proc.pid
            }
            username = str(redis_client.hget(f"sid:{sid}", "username"))
            redis_client.hset(f"session:{session['id']}", mapping=session)
            redis_client.hset(f"sid:{sid}", "session_id", session['id'])
            redis_client.sadd(f"sessions:user:{username}", session['id'])
            
            return session["id"]

    async def disconnect_active_session(self, sid) -> None:
        session_id = redis_client.hget(f"sid:{sid}", "session_id")
        if session_id:
            redis_client.hincrby(f"session:{session_id}", "players", -1)
            redis_client.hdel(f"sid:{sid}", "session_id")
        
        sock = SOCKETS_MAPPING.get(sid, None)
        if sock:
            sock.close()
            del SOCKETS_MAPPING[sid]

    async def join_session(self, sid: str, session_id: str) -> socket.socket:
        session = self.get_session_by_id(session_id)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        await asyncio.get_event_loop().sock_connect(sock, ("localhost", session["port"]))
        redis_client.hincrby(f"session:{session_id}", "players", 1)
        SOCKETS_MAPPING[sid] = sock

        return sock

    async def terminate_session(self, sid: str) -> str | None:
        session_id = self.get_active_session(sid)
        if session_id:
            session = self.get_session_by_id(session_id)
            await self.send_command(sid, 0, None)
            username = str(redis_client.hget(f"sid:{sid}", "username"))
            self.release_port(session["port"])
            redis_client.srem(f"session:user:{username}", session_id)
            redis_client.delete(f"session:{session_id}")

        return session_id

    async def read_message(self, sid: str):
        try:
            sock = SOCKETS_MAPPING.get(sid, None)
            if not sock:
                return None, None, None
            
            cmd_data = await asyncio.get_event_loop().sock_recv(sock, 2)
            if not cmd_data:
                return None, None, None

            cmd = int.from_bytes(cmd_data, "little")
            
            # Receive buffer size (4 bytes, for example)
            buff_size_data = await asyncio.get_event_loop().sock_recv(sock, 4)
            buff_size = int.from_bytes(buff_size_data, "little")

            # Receive the actual data
            data = b""
            while len(data) < buff_size:
                chunk = await asyncio.get_event_loop().sock_recv(sock, buff_size - len(data))
                if not chunk:
                    break
                data += chunk
            
            return cmd, buff_size, data
        except ConnectionResetError:
            log.error("Connection lost with the session")

    async def send_command(self, sid: str, command: int, data: int):
        try:
            sock = SOCKETS_MAPPING.get(sid, None)
            if not sock:
                return
            
            size = 2 if data is not None else 0
            await asyncio.get_event_loop().sock_sendall(sock, struct.pack("h", command))
            await asyncio.get_event_loop().sock_sendall(sock, struct.pack("i", size))
            if data is not None:
                await asyncio.get_event_loop().sock_sendall(sock, struct.pack("h", data))
        except BrokenPipeError:
            pass

emulation_session_handler = EmulationSessionHandler(range(9000, 9100))