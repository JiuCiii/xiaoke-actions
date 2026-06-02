from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal


DeviceName = Literal["main", "vibrator"]

FFE1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
MAIN_ADDRESS = "33:74:7E:ED:80:D9"
VIBRATOR_ADDRESS = "3D:B2:B4:ED:41:68"
MAX_SECONDS = 30
BLE_OPERATION_SECONDS = 8


class ToyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ToyActionResult:
    ok: bool
    action: str
    device: str
    address: str | None
    reason: str
    seconds: float | None = None
    mode: int | None = None
    level: int | None = None


def _command(function_code: int, mode: int, parameter: int) -> bytes:
    return bytes([0x55, function_code, 0x00, 0x00, mode, parameter, 0x00])


def _main_command(mode: int) -> bytes:
    return _command(0x09, mode, 0x01)


def _vibe_command(level: int) -> bytes:
    return _command(0x03, 0x01, level)


def _stop_commands() -> tuple[bytes, ...]:
    return (
        _command(0x09, 0x00, 0x00),
        _command(0x08, 0x00, 0x00),
        _command(0x03, 0x00, 0x00),
    )


def _clean_seconds(seconds: float) -> float:
    if seconds <= 0:
        raise ToyError("seconds_must_be_positive")
    return min(seconds, MAX_SECONDS)


def _address_for(device: DeviceName) -> str:
    if device == "main":
        return MAIN_ADDRESS
    if device == "vibrator":
        return VIBRATOR_ADDRESS
    raise ToyError("unknown_device")


class ToyController:
    async def main(self, mode: int, seconds: float) -> ToyActionResult:
        if not 1 <= mode <= 10:
            raise ToyError("main_mode_must_be_1_10")
        duration = _clean_seconds(seconds)
        address = _address_for("main")
        await self._run_for(address, _main_command(mode), duration)
        return ToyActionResult(
            ok=True,
            action="main",
            device="main",
            address=address,
            reason="sent",
            seconds=duration,
            mode=mode,
        )

    async def vibe(self, level: int, seconds: float) -> ToyActionResult:
        if not 1 <= level <= 6:
            raise ToyError("vibe_level_must_be_1_6")
        duration = _clean_seconds(seconds)
        address = _address_for("vibrator")
        await self._run_for(address, _vibe_command(level), duration)
        return ToyActionResult(
            ok=True,
            action="vibe",
            device="vibrator",
            address=address,
            reason="sent",
            seconds=duration,
            level=level,
        )

    async def start_main(self, mode: int) -> ToyActionResult:
        if not 1 <= mode <= 10:
            raise ToyError("main_mode_must_be_1_10")
        address = _address_for("main")
        await self._write_once(address, _main_command(mode))
        return ToyActionResult(
            ok=True,
            action="main",
            device="main",
            address=address,
            reason="started",
            mode=mode,
        )

    async def start_vibe(self, level: int) -> ToyActionResult:
        if not 1 <= level <= 6:
            raise ToyError("vibe_level_must_be_1_6")
        address = _address_for("vibrator")
        await self._write_once(address, _vibe_command(level))
        return ToyActionResult(
            ok=True,
            action="vibe",
            device="vibrator",
            address=address,
            reason="started",
            level=level,
        )

    async def stop_device(self, device: DeviceName) -> ToyActionResult:
        address = _address_for(device)
        await self._stop(address)
        return ToyActionResult(
            ok=True,
            action="stop",
            device=device,
            address=address,
            reason="sent",
        )

    async def stop(self, device: Literal["main", "vibrator", "all"] = "all") -> list[ToyActionResult]:
        devices: tuple[DeviceName, ...]
        if device == "all":
            devices = ("main", "vibrator")
        elif device in ("main", "vibrator"):
            devices = (device,)
        else:
            raise ToyError("unknown_device")

        results: list[ToyActionResult] = []
        for current in devices:
            address = _address_for(current)
            try:
                await self._stop(address)
            except Exception as exc:
                results.append(
                    ToyActionResult(
                        ok=False,
                        action="stop",
                        device=current,
                        address=address,
                        reason=str(exc),
                    )
                )
            else:
                results.append(
                    ToyActionResult(
                        ok=True,
                        action="stop",
                        device=current,
                        address=address,
                        reason="sent",
                    )
                )
        return results

    def status(self) -> dict:
        return {
            "devices": {
                "main": {
                    "address": MAIN_ADDRESS,
                    "modes": "1-10",
                    "note": "Circle-button frequency in the current manual function group.",
                },
                "vibrator": {
                    "address": VIBRATOR_ADDRESS,
                    "levels": "1-6",
                    "note": "Separate SX176A-02 vibrator.",
                },
            },
            "max_seconds": MAX_SECONDS,
            "requires_duration": True,
        }

    async def _run_for(self, address: str, command: bytes, seconds: float) -> None:
        async def operation() -> None:
            BleakClient = _bleak_client()
            async with BleakClient(address, timeout=BLE_OPERATION_SECONDS) as client:
                await self._stop_connected(client)
                await asyncio.sleep(0.25)
                await client.write_gatt_char(FFE1, command, response=False)
                await asyncio.sleep(seconds)
                await self._stop_connected(client)

        await asyncio.wait_for(operation(), timeout=seconds + BLE_OPERATION_SECONDS + 3)

    async def _stop(self, address: str) -> None:
        async def operation() -> None:
            BleakClient = _bleak_client()
            async with BleakClient(address, timeout=BLE_OPERATION_SECONDS) as client:
                await self._stop_connected(client)

        await asyncio.wait_for(operation(), timeout=BLE_OPERATION_SECONDS + 3)

    async def _write_once(self, address: str, command: bytes) -> None:
        async def operation() -> None:
            BleakClient = _bleak_client()
            async with BleakClient(address, timeout=BLE_OPERATION_SECONDS) as client:
                await self._stop_connected(client)
                await asyncio.sleep(0.25)
                await client.write_gatt_char(FFE1, command, response=False)

        await asyncio.wait_for(operation(), timeout=BLE_OPERATION_SECONDS + 3)

    async def _stop_connected(self, client: Any) -> None:
        for command in _stop_commands():
            await client.write_gatt_char(FFE1, command, response=False)


def _bleak_client() -> Any:
    try:
        from bleak import BleakClient
    except ImportError as exc:
        raise ToyError("bleak_not_installed") from exc
    return BleakClient
