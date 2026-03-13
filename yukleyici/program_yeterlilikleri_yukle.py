#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

from api_runtime import auth_headers, find_bolum_id, login, pick_year_id_with_offerings, resolve_base_url


DEFAULT_BASE_URL = ""
DEFAULT_EMAIL = "admin@gop.edu.tr"
DEFAULT_PASSWORD = "admin123"
DEFAULT_INPUT_JSON = Path(__file__).resolve().parents[1] / "program_yeterlilikleri.json"
DEFAULT_REPORT_JSON = Path(__file__).resolve().with_name("program_yeterlilikleri_yukle_sonuc.json")
TARGET_BOLUM_KEYWORD = "bilgisayar"


def normalize_code(value: str) -> str | None:
    match = re.fullmatch(r"P\s*Y?\s*(\d+)", (value or "").strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return f"PY{int(match.group(1))}"


def request_json(method: str, url: str, *, headers: dict, timeout: int, verify_ssl: bool, payload=None, params=None):
    response = requests.request(
        method=method.upper(),
        url=url,
        headers=headers,
        json=payload,
        params=params,
        timeout=timeout,
        verify=verify_ssl,
    )
    response.raise_for_status()
    if not response.text:
        return None
    return response.json()


def load_program_outcomes(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    items = payload.get("program_yeterlilikleri") or []
    normalized: list[dict[str, str]] = []
    for item in items:
        code = normalize_code(str(item.get("kod") or ""))
        description = " ".join(str(item.get("aciklama") or "").split())
        if not code or not description:
            continue
        normalized.append({"kod": code, "aciklama": description})
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description="Program yeterliliklerini API'ye create/update olarak yukler")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API veya site URL")
    parser.add_argument("--live", action="store_true", help="Canli ortami otomatik secer")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--input-json", default=str(DEFAULT_INPUT_JSON))
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--bolum-id", default=None)
    parser.add_argument("--bolum-keyword", default=TARGET_BOLUM_KEYWORD)
    parser.add_argument("--year-id", default=None)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    if not input_path.exists():
        raise SystemExit(f"Girdi dosyasi bulunamadi: {input_path}")

    outcomes = load_program_outcomes(input_path)
    if not outcomes:
        raise SystemExit("Yuklenecek program yeterliligi bulunamadi")

    verify_ssl = not args.insecure
    base_url = resolve_base_url(args.base_url, args.live)
    token = login(base_url, args.email, args.password, timeout=args.timeout, verify_ssl=verify_ssl)

    bolum_id = args.bolum_id or find_bolum_id(
        base_url,
        token,
        keyword=args.bolum_keyword,
        timeout=args.timeout,
        verify_ssl=verify_ssl,
    )
    year_id = pick_year_id_with_offerings(
        base_url,
        token,
        bolum_id,
        explicit_year_id=args.year_id,
        timeout=args.timeout,
        verify_ssl=verify_ssl,
    )

    headers = auth_headers(token)
    existing_items = request_json(
        "GET",
        f"{base_url}/outcomes",
        headers=headers,
        timeout=args.timeout,
        verify_ssl=verify_ssl,
        params={"akademikYilId": year_id, "bolumId": bolum_id},
    ) or []
    existing_by_code = {}
    for item in existing_items:
        code = normalize_code(str(item.get("Kod") or item.get("kod") or ""))
        if code:
            existing_by_code[code] = item

    created_codes: list[str] = []
    updated_codes: list[str] = []
    unchanged_codes: list[str] = []

    for outcome in outcomes:
        code = outcome["kod"]
        description = outcome["aciklama"]
        existing = existing_by_code.get(code)

        if existing is None:
            if not args.dry_run:
                request_json(
                    "POST",
                    f"{base_url}/outcomes",
                    headers=headers,
                    timeout=args.timeout,
                    verify_ssl=verify_ssl,
                    payload={
                        "akademikYilId": year_id,
                        "kod": code,
                        "aciklama": description,
                        "bolumId": bolum_id,
                    },
                )
            created_codes.append(code)
            continue

        existing_id = existing.get("Id") or existing.get("id")
        existing_description = " ".join(str(existing.get("Aciklama") or existing.get("aciklama") or "").split())
        if existing_description == description:
            unchanged_codes.append(code)
            continue

        if not args.dry_run:
            request_json(
                "PUT",
                f"{base_url}/outcomes/{existing_id}",
                headers=headers,
                timeout=args.timeout,
                verify_ssl=verify_ssl,
                payload={
                    "kod": code,
                    "aciklama": description,
                    "bolumId": bolum_id,
                },
            )
        updated_codes.append(code)

    report = {
        "base_url": base_url,
        "bolum_id": bolum_id,
        "year_id": year_id,
        "input_json": str(input_path),
        "dry_run": args.dry_run,
        "source_count": len(outcomes),
        "created_codes": created_codes,
        "updated_codes": updated_codes,
        "unchanged_codes": unchanged_codes,
    }

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(f"Rapor yazildi: {report_path}")
    print(f"Toplam kaynak yeterlilik: {len(outcomes)}")
    print(f"Olusturulan: {len(created_codes)}")
    print(f"Guncellenen: {len(updated_codes)}")
    print(f"Degismeyen: {len(unchanged_codes)}")
    if args.dry_run:
        print("Dry-run: API'ye yazma yapilmadi.")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else str(exc)
        print(f"HATA: HTTP {exc.response.status_code if exc.response is not None else '?'} {body}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        sys.exit(1)