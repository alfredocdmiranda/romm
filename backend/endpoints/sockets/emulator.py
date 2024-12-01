from __future__ import annotations

from pathlib import Path

from config import LIBRARY_BASE_PATH
from handler.emulation_session_handler import emulation_session_handler
from handler.database import db_rom_handler
from handler.socket_handler import socket_handler
from logger.logger import log
from models.platform import Platform
from models.rom import Rom
import base64
import struct

# This is harded coded for tests
MAPPING_CORES = {
    "snes": "snes9x_libretro.so",
    # "n64": "mupen64plus_next_libretro.so",  # TODO Still need to make it work in retro-server
}



@socket_handler.socket_server.on("disconnect")
async def disconnect(sid):
    """
    It clears the sessions
    """
    # TODO This should be moved to a more centralized place
    # user_id = sid_user_id[sid]
    await emulation_session_handler.disonnect_active_session(sid)
    log.debug(f"Socket [{sid}] disconnected.")


@socket_handler.socket_server.on("emulation:disconnect")
async def emulation_disconnect(sid, options: dict[str, str]):
    """
    It clears the sessions
    """
    # TODO This should be moved to a more centralized place
    # user_id = sid_user_id[sid]
    await emulation_session_handler.disonnect_active_session(sid)
    log.debug(f"Socket [{sid}] disconnected.")


@socket_handler.socket_server.on("emulation:exit")
async def emulation_exit(sid, options: dict[str, str]):
    """It exits the session (terminates the emulation)"""
    # user_id = int(options["userId"])
    await emulation_session_handler.terminate_session(sid)
    log.error("Session exited")


@socket_handler.socket_server.on("emulation:create")
async def emulation_create(sid, options: dict[str, str]):
    """It creates a new session. It will instantiate a new retro-server process."""
    # TODO Need to find a way to get the actual user_id
    # sid_user_id[sid] = int(options["userId"])
    # user_id = sid_user_id[sid]
    rom = db_rom_handler.get_rom(int(options["romId"]))
    rom_path = Path(LIBRARY_BASE_PATH, rom.full_path)
    session_id = await emulation_session_handler.create_session(sid, MAPPING_CORES[rom.platform.slug], rom_path)
    await socket_handler.socket_server.emit('emulation:create', {'data': session_id}, to=sid)


@socket_handler.socket_server.on("emulation:join")
async def emulation_join(sid, options: dict[str, str]):
    """User connect"""
    # sid_user_id[sid] = int(options["userId"])
    log.error(f"JOINING THE SESSION {options["sessionId"]}")
    session_id = options["sessionId"]
    await socket_handler.socket_server.emit('emulation:create', {'data': session_id}, to=sid)


@socket_handler.socket_server.on("emulation:run")
async def emulation_run(sid, options: dict[str, str]):
    """User connect"""

    session_id = options["sessionId"]
    log.warning(f"Session ID: {session_id}")
    # user_id = sid_user_id[sid]
    session = emulation_session_handler.get_session_by_id(session_id)
    await session.connect(sid)
    while True:
        cmd, _, data = await session.read_mesages(sid)
        if cmd == 1:
            await socket_handler.socket_server.emit('emulation:audio', {'data': data}, to=sid)
        elif cmd == 2:
            await socket_handler.socket_server.emit('emulation:video', {'data': base64.b64encode(data).decode("utf-8")}, to=sid)
        elif cmd == 3:
            ratio, width, height, fps, audio_sample = struct.unpack("ddddd", data)
            await socket_handler.socket_server.emit('emulation:config', {'data': {"audio_sample": audio_sample}}, to=sid)


@socket_handler.socket_server.on("emulation:command")
async def emulation_command(sid, options: dict[str, str]):
    # user_id = sid_user_id[sid]
    session_id = options["sessionId"]
    session = emulation_session_handler.get_session_by_id(session_id)

    cmd = int(options["data"]["command"])
    data = options["data"].get("data", None)
    data = int(data) if data is not None else data
    await session.send_command(sid, cmd, data)
