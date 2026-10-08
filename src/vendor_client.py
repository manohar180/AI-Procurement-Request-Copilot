from __future__ import annotations

import os
import socket
from urllib.parse import quote, urlparse
import requests


def _is_server_listening(base_url: str) -> bool:
    """Quickly check if the local server host/port is open without waiting for long TCP timeouts."""
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 8001
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def get_vendor_risk(vendor_name: str, timeout_seconds: float = 3.0) -> dict:
    """Low-level API client for the mock vendor-risk service.

    Queries the live HTTP endpoint if running, or falls back to in-process TestClient
    if the local service process has not been started separately.
    """
    base_url = os.getenv("VENDOR_RISK_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
    url = f"{base_url}/vendor-risk/{quote(vendor_name, safe='')}"

    if _is_server_listening(base_url):
        try:
            response = requests.get(url, timeout=timeout_seconds)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError:
            raise
        except requests.RequestException:
            pass

    # In-process mock API execution for standalone evaluation runs when server process is not up
    from fastapi.testclient import TestClient
    from mock_api.app import app

    client = TestClient(app)
    res = client.get(f"/vendor-risk/{quote(vendor_name, safe='')}")
    if res.status_code == 503:
        raise requests.HTTPError(
            f"503 Server Error: Service Unavailable for url: {url} - {res.text}",
            response=None,
        )
    elif res.status_code == 404:
        raise requests.HTTPError(
            f"404 Client Error: Not Found for url: {url} - {res.text}",
            response=None,
        )
    elif res.status_code != 200:
        raise requests.HTTPError(
            f"{res.status_code} Error for url: {url} - {res.text}",
            response=None,
        )
    return res.json()
