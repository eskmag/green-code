"""Liten HTTP-klient mot green-code-API-et. Bare standardbiblioteket."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Optional


class ApiError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str, token: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _post(self, path: str, body: dict[str, Any]) -> Optional[dict[str, Any]]:
        req = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token}",
                     "User-Agent": "greencode-worker/0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 204:
                    return None
                return json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            raise ApiError(f"{e.code} fra {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"Får ikke kontakt med {self.base_url}: {e.reason}") from e

    def claim(self, worker_id: str) -> Optional[dict[str, Any]]:
        return self._post("/api/v1/worker/claim", {"worker_id": worker_id})

    def submit(self, analysis_id: int, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
        return self._post(f"/api/v1/worker/analyses/{analysis_id}/result", payload)
