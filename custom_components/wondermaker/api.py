"""Minimaler asynchroner Moonraker-Client."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp


class MoonrakerError(Exception):
    """Allgemeiner Fehler."""


class MoonrakerAuthError(MoonrakerError):
    """Authentifizierung fehlgeschlagen (401/403)."""


class MoonrakerConnectionError(MoonrakerError):
    """Verbindung nicht möglich."""


class MoonrakerClient:
    """Spricht die HTTP-API von Moonraker an."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 7125,
        api_key: str | None = None,
    ) -> None:
        self._session = session
        self.host = host
        self.port = port
        self._api_key = api_key

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self._api_key} if self._api_key else {}

    def resolve_url(self, url: str | None) -> str | None:
        """Webcam-URLs sind oft relativ (z. B. /webcam/?action=stream)."""
        if not url:
            return None
        if url.startswith(("http://", "https://")):
            return url
        if url.startswith("/"):
            # Relative Pfade liegen meist hinter dem Webserver (Port 80)
            return f"http://{self.host}{url}"
        return f"http://{self.host}/{url}"

    def candidate_urls(self, url: str | None) -> list[str]:
        """Moonraker meldet relative Webcam-URLs (/webcam/...). Üblich sind der
        Webserver auf Port 80 oder crowsnest/ustreamer direkt auf Port 8080."""
        primary = self.resolve_url(url)
        if not primary:
            return []
        result = [primary]
        if url and url.startswith("/webcam"):
            result.append(f"http://{self.host}:8080{url[len('/webcam'):]}")
        return result

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        raw: bool = False,
        timeout: float = 10,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with asyncio.timeout(timeout):
                async with self._session.request(
                    method, url, params=params, json=json, headers=self._headers
                ) as resp:
                    if resp.status in (401, 403):
                        raise MoonrakerAuthError(f"HTTP {resp.status}: nicht autorisiert")
                    if resp.status >= 400:
                        text = await resp.text()
                        raise MoonrakerError(f"HTTP {resp.status}: {text[:200]}")
                    if raw:
                        return await resp.read()
                    payload = await resp.json(content_type=None)
        except MoonrakerError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MoonrakerConnectionError(str(err) or type(err).__name__) from err
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    # --- Lesen ---------------------------------------------------------
    async def server_info(self) -> dict[str, Any]:
        return await self._request("GET", "/server/info")

    async def printer_info(self) -> dict[str, Any]:
        return await self._request("GET", "/printer/info")

    async def list_objects(self) -> list[str]:
        result = await self._request("GET", "/printer/objects/list")
        return list(result.get("objects", []))

    async def query_objects(self, names: list[str]) -> dict[str, Any]:
        result = await self._request(
            "POST",
            "/printer/objects/query",
            json={"objects": {name: None for name in names}},
        )
        return result.get("status", {})

    async def proc_stats(self) -> dict[str, Any]:
        return await self._request("GET", "/machine/proc_stats")

    async def webcams(self) -> list[dict[str, Any]]:
        result = await self._request("GET", "/server/webcams/list")
        return list(result.get("webcams", []))

    async def file_metadata(self, filename: str) -> dict[str, Any]:
        return await self._request(
            "GET", "/server/files/metadata", params={"filename": filename}
        )

    async def get_gcode_file(self, relative_path: str) -> bytes:
        return await self._request(
            "GET", f"/server/files/gcodes/{quote(relative_path)}", raw=True
        )

    async def get_url_bytes(self, url: str, timeout: float = 10) -> bytes:
        try:
            async with asyncio.timeout(timeout):
                async with self._session.get(url, headers=self._headers) as resp:
                    if resp.status >= 400:
                        raise MoonrakerError(f"HTTP {resp.status}")
                    return await resp.read()
        except MoonrakerError:
            raise
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MoonrakerConnectionError(str(err) or type(err).__name__) from err

    # --- Steuern -------------------------------------------------------
    async def gcode(self, script: str, timeout: float = 30) -> None:
        await self._request(
            "POST", "/printer/gcode/script", params={"script": script}, timeout=timeout
        )

    async def pause(self) -> None:
        await self._request("POST", "/printer/print/pause")

    async def resume(self) -> None:
        await self._request("POST", "/printer/print/resume")

    async def cancel(self) -> None:
        await self._request("POST", "/printer/print/cancel")

    async def start_print(self, filename: str) -> None:
        await self._request("POST", "/printer/print/start", params={"filename": filename})

    async def emergency_stop(self) -> None:
        await self._request("POST", "/printer/emergency_stop")

    async def firmware_restart(self) -> None:
        await self._request("POST", "/printer/firmware_restart")

    async def klipper_restart(self) -> None:
        await self._request("POST", "/printer/restart")
