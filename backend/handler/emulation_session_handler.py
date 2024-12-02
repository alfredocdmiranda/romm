import asyncio
import socket
import struct
import subprocess
import uuid
from enum import Enum
from logger.logger import log
from pathlib import Path

RETRO_SERVER_BIN = "/bin/retro_server"
LIBRETRO_PATH = "/romm/libretro"


class EmulatorCommands(Enum):
    AUDIO = 1
    VIDEO = 2
    CONFIG = 3


class Session:
    def __init__(self, port, core, file, process):
        self.id = str(uuid.uuid4())
        self.port = port
        self.core = core
        self.file = file
        self.process = process
        self._sockets = {}
        self.state = 0
    
    async def connect(self, sid):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        await asyncio.get_event_loop().sock_connect(sock, ("localhost", self.port))

        self._sockets[sid] = sock
        return sock
    
    async def disconnect(self, sid):
        sock = self._sockets[sid]
        sock.close()
        log.error("SOCKET CLOSED")
        del self._sockets[sid]
    
    async def send_command(self, sid, command, data):
        try:
            sock = self._sockets[sid]
            size = 2 if data is not None else 0
            await asyncio.get_event_loop().sock_sendall(sock, struct.pack("h", command))
            await asyncio.get_event_loop().sock_sendall(sock, struct.pack("i", size))
            if data is not None:
                await asyncio.get_event_loop().sock_sendall(sock, struct.pack("h", data))
        except BrokenPipeError:
            pass

    async def read_mesages(self, sid):
        try:
            sock = self._sockets[sid]
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
            poll = self.process.poll()
            if poll is None:
                log.warning("Process died!!!")
            else:
                log.warning("Process DID NOT die!!!")


class EmulationSessionHandler:
    def __init__(self, port_range):
        self._sessions: list[Session] = []
        self._sessions_by_id: dict[str, Session] = {}
        self._sessions_by_sid: dict[str, Session] = {}
        # TODO A user may have multiple sessions active, however only one per socket. 
        # Also, they might have sessions that are paused. Still need to work this out.
        self._sessions_by_user: dict[int, Session] = {}
        self._used_ports = set()
        self._port_range = port_range

    
    def get_session_by_id(self, id_: str) -> Session | None:
        return self._sessions_by_id.get(id_, None)
    
    def get_session_by_sid(self, sid: str) -> Session | None:
        """
        Returns a object Session for a Socket ID.
        """
        return self._sessions_by_sid.get(sid, None)

    def get_sessions_by_user_id(self, id_: str):
        return self._sessions_by_user[int(id_)]
    
    def get_avaliable_port(self):
        for i in self._port_range:
            if i not in self._used_ports:
                return i
    
    async def create_session(self, sid, core, filepath, port=None):
        try:
            rs_proc = None
            libretro_core = Path(LIBRETRO_PATH, core)
            port = self.get_avaliable_port()
            if port is None:
                raise ValueError("No Port is Available")
            log.info(f"{libretro_core} {filepath} {port}")
            rs_proc = subprocess.Popen([RETRO_SERVER_BIN, "-p", str(port), libretro_core, filepath])
            await asyncio.sleep(1)
            poll = rs_proc.poll()
            if poll is not None:
                raise ValueError("Process Died")
        except BaseException as err:
            log.exception(f"Some Error: {err}")
            if rs_proc is not None:
                rs_proc.kill()
        else:
            session = Session(port, core, filepath, rs_proc)
            self._used_ports.add(port)
            self._sessions.append(session)
            self._sessions_by_id[session.id] = session
            self._sessions_by_sid[sid] = session
            # self._sessions_by_user[user_id] = session
            return session.id

    async def disconnect_active_session(self, sid) -> None:
        session = self.get_session_by_sid(sid)
        if session:
            await session.disconnect(sid)

    async def join_session(self, sid: str, session_id: str):
        session = self.get_session_by_id(session)
        if session:
            session.connect(sid)

    async def terminate_session(self, sid: str) -> str | None:
        session = self.get_session_by_sid(sid)
        if session:
            await session.send_command(sid, 0, None)
            used_port = session.port
            self._used_ports.remove(used_port)
            self._sessions.remove(session)
            del self._sessions_by_id[session.id]
            del self._sessions_by_sid[sid]

            return session.id


emulation_session_handler = EmulationSessionHandler(range(9000, 9010))