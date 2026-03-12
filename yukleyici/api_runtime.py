import os
from urllib.parse import urlparse

import requests

LOCAL_BASE_URL = "http://localhost:4000/dpks-api"
LIVE_SITE_URL = "https://yzdd.gop.edu.tr/dpks"
LIVE_API_URL = "https://yzdd.gop.edu.tr/dpks-api"


def normalize_base_url(raw_url: str | None) -> str:
    """Normalizes site/api URL to a usable dpks-api base URL."""
    url = (raw_url or "").strip()
    if not url:
        return LOCAL_BASE_URL

    url = url.rstrip("/")
    if url.endswith("/dpks-api"):
        return url
    if url.endswith("/dpks"):
        return f"{url[:-5]}/dpks-api"
    return f"{url}/dpks-api"


def resolve_base_url(base_url: str | None, live: bool = False) -> str:
    if live:
        return LIVE_API_URL
    env_base = os.getenv("DPKS_API_BASE")
    return normalize_base_url(base_url or env_base or LOCAL_BASE_URL)


def api_host(base_url: str) -> str:
    return urlparse(base_url).netloc.lower()


def is_local_api(base_url: str) -> bool:
    host = api_host(base_url)
    return host.startswith("localhost") or host.startswith("127.0.0.1")


def login(base_url: str, email: str, password: str, timeout: int = 20, verify_ssl: bool = True) -> str:
    r = requests.post(
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=timeout,
        verify=verify_ssl,
    )
    r.raise_for_status()
    token = r.json().get("token")
    if not token:
        raise RuntimeError(f"Token alinamadi: {r.text}")
    return token


def auth_headers(token: str, with_json: bool = True) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    if with_json:
        headers["Content-Type"] = "application/json"
    return headers


def find_bolum_id(base_url: str, token: str, keyword: str = "bilgisayar", timeout: int = 20, verify_ssl: bool = True) -> str:
    r = requests.get(
        f"{base_url}/bolumler",
        headers=auth_headers(token),
        timeout=timeout,
        verify=verify_ssl,
    )
    r.raise_for_status()
    items = r.json()
    kw = keyword.lower()
    for b in items:
        ad = (b.get("ad") or b.get("Ad") or "").lower()
        kod = (b.get("kod") or b.get("Kod") or "").lower()
        if kw in ad or kw in kod:
            return b.get("id") or b.get("Id")
    raise RuntimeError(f"'{keyword}' iceren bolum bulunamadi")


def pick_year_id_with_offerings(base_url: str, token: str, bolum_id: str, explicit_year_id: str | None = None, timeout: int = 20, verify_ssl: bool = True) -> str:
    if explicit_year_id:
        return explicit_year_id

    r = requests.get(
        f"{base_url}/academic-years",
        headers=auth_headers(token),
        timeout=timeout,
        verify=verify_ssl,
    )
    r.raise_for_status()
    years = r.json() or []

    years = sorted(
        years,
        key=lambda y: str(y.get("yilKodu") or y.get("YilKodu") or ""),
        reverse=True,
    )

    for y in years:
        year_id = y.get("id") or y.get("Id")
        if not year_id:
            continue
        off = requests.get(
            f"{base_url}/offerings",
            params={"akademikYilId": year_id, "bolumId": bolum_id},
            headers=auth_headers(token),
            timeout=timeout,
            verify=verify_ssl,
        )
        if off.ok and isinstance(off.json(), list) and len(off.json()) > 0:
            return year_id

    if years:
        return years[0].get("id") or years[0].get("Id")

    raise RuntimeError("Akademik yil bulunamadi")
