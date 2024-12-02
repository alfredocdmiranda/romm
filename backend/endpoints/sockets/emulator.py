from __future__ import annotations

import base64
import struct
from pathlib import Path

from config import LIBRARY_BASE_PATH
from handler.emulation_session_handler import EmulatorCommands, emulation_session_handler
from handler.database import db_rom_handler, db_user_handler
from handler.socket_handler import socket_handler
from logger.logger import log
from models.platform import Platform
from models.rom import Rom


# This is harded coded for tests
MAPPING_CORES = {
    "snes": "snes9x_libretro.so",
    # "n64": "mupen64plus_next_libretro.so",  # TODO Still need to make it work in retro-server
}

@socket_handler.socket_server.on("emulation:disconnect")
async def emulation_disconnect(sid, options: dict[str, str]):
    """
    Executed when user exits the view or the socket is closed
    """
    user_id = socket_handler.get_user_id(sid)
    await emulation_session_handler.disconnect_active_session(sid)
    log.debug(f"Socket [{user_id}][{sid}] disconnected.")


@socket_handler.socket_server.on("emulation:exit")
async def emulation_exit(sid, options: dict[str, str]):
    """It exits the session (terminates the emulation)"""
    session_id = await emulation_session_handler.terminate_session(sid)
    log.debug(f"Session [{session_id}] exited")


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
    """
    It start to run the emulation. It reads the messages from the emulator and send to the clients.
    """

    session = emulation_session_handler.get_session_by_sid(sid)
    if not session:
        session_id = options["sessionId"]
        session = emulation_session_handler.get_session_by_id(session_id)
    
    await session.connect(sid)
    while True:
        cmd, _, data = await session.read_mesages(sid)
        if cmd is None:
            break
        cmd = EmulatorCommands(cmd)
        match cmd:
            case EmulatorCommands.AUDIO:
                await socket_handler.socket_server.emit('emulation:audio', {'data': data}, to=sid)
            case EmulatorCommands.VIDEO:
                await socket_handler.socket_server.emit('emulation:video', {'data': base64.b64encode(data).decode("utf-8")}, to=sid)
            case EmulatorCommands.CONFIG:
                ratio, width, height, fps, audio_sample = struct.unpack("ddddd", data)
                json_data = {
                    "audio_sample": audio_sample,
                    "ratio": ratio,
                    "width": width,
                    "height": height,
                    "fps": fps
                }
                await socket_handler.socket_server.emit('emulation:config', {'data': json_data}, to=sid)


@socket_handler.socket_server.on("emulation:command")
async def emulation_command(sid, options: dict[str, str]):
    """
    It receives command from the client and send to the emulator
    """
    session = emulation_session_handler.get_session_by_sid(sid)

    cmd = int(options["data"]["command"])
    data = options["data"].get("data", None)
    data = int(data) if data is not None else data
    await session.send_command(sid, cmd, data)
