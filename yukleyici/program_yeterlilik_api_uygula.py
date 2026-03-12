#!/usr/bin/env python3
"""
Bilgisayar Muhendisligi bolumu dersleri icin program yeterlilik matrisini
API uzerinden toplu uygular.

Kaynak:
- ders_planlari_cikti/ders_program_yeterlilikleri.json

Hedef API:
- POST /dpks-api/auth/login
- GET  /dpks-api/bolumler
- GET  /dpks-api/academic-years
- GET  /dpks-api/offerings?akademikYilId=...&bolumId=...
- GET  /dpks-api/outcomes?akademikYilId=...
- POST /dpks-api/outcomes
- PUT  /dpks-api/matrix/bulk
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from api_runtime import resolve_base_url

DEFAULT_BASE_URL = ""
DEFAULT_EMAIL = "admin@gop.edu.tr"
DEFAULT_PASSWORD = "admin123"
DEFAULT_MAPPING = str(Path(__file__).resolve().parents[1] / "ders_program_yeterlilikleri.json")
DEFAULT_REPORT = str(Path(__file__).resolve().with_name("program_yeterlilik_api_sonuc.json"))
TARGET_BOLUM_KEYWORD = "bilgisayar"
MAX_PY = 11


class ApiError(RuntimeError):
    pass


@dataclass
class ApiClient:
    base_url: str
    token: str | None = None

    def _url(self, path: str, query: dict[str, Any] | None = None) -> str:
        p = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url.rstrip('/')}{p}"
        if query:
            q = {k: v for k, v in query.items() if v is not None and v != ""}
            if q:
                url += "?" + parse.urlencode(q)
        return url

    def request_json(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        url = self._url(path, query)
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = request.Request(url=url, method=method.upper(), headers=headers, data=data)
        try:
            with request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8")
                if not body:
                    return None
                return json.loads(body)
        except error.HTTPError as ex:
            body = ex.read().decode("utf-8", errors="ignore")
            raise ApiError(f"HTTP {ex.code} {method} {path}: {body}") from ex
        except error.URLError as ex:
            raise ApiError(f"Baglanti hatasi ({method} {path}): {ex}") from ex


def normalize_py_code(value: str) -> str | None:
    s = (value or "").strip().upper()
    if not s:
        return None

    m = re.fullmatch(r"PY\s*(\d+)", s)
    if m:
        n = int(m.group(1))
        return f"PY{n}" if 1 <= n <= MAX_PY else None

    m = re.fullmatch(r"P\s*(\d+)", s)
    if m:
        n = int(m.group(1))
        return f"PY{n}" if 1 <= n <= MAX_PY else None

    m = re.search(r"(\d+)", s)
    if m:
        n = int(m.group(1))
        return f"PY{n}" if 1 <= n <= MAX_PY else None

    return None


def parse_score(raw: Any) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "--"}:
        return None
    m = re.search(r"\d+", s)
    if not m:
        return None
    v = int(m.group(0))
    if v <= 0:
        return None
    return min(v, 5)


def pick_bolum_id(bolumler: list[dict[str, Any]], keyword: str) -> str:
    keyword = keyword.lower()
    for b in bolumler:
        ad = (b.get("Ad") or b.get("ad") or "").lower()
        kod = (b.get("Kod") or b.get("kod") or "").lower()
        if keyword in ad or keyword in kod:
            return b.get("Id") or b.get("id")
    raise ApiError(f"'{keyword}' iceren bolum bulunamadi")


def pick_year_id(years: list[dict[str, Any]], explicit_id: str | None) -> str:
    if explicit_id:
        return explicit_id

    def year_key(item: dict[str, Any]) -> str:
        return str(item.get("yilKodu") or item.get("YilKodu") or "")

    sorted_years = sorted(years, key=year_key, reverse=True)
    if not sorted_years:
        raise ApiError("Akademik yil bulunamadi")

    for y in sorted_years:
        durum = (y.get("durum") or y.get("Durum") or "").upper()
        if durum in {"YAYIN", "ONAY", "ONAY_BEKLIYOR", "TASLAK"}:
            return y.get("id") or y.get("Id")

    return sorted_years[0].get("id") or sorted_years[0].get("Id")


def pick_year_with_offerings(
    api: ApiClient,
    years: list[dict[str, Any]],
    bolum_id: str,
    explicit_id: str | None,
) -> str:
    """Bolum icin dersi olan en guncel akademik yili secer.

    Explicit year verilirse onu kullanir.
    Explicit yoksa, son yildan baslayip offerings > 0 olan ilk yili secer.
    """
    if explicit_id:
        return explicit_id

    sorted_years = sorted(
        years,
        key=lambda y: str(y.get("yilKodu") or y.get("YilKodu") or ""),
        reverse=True,
    )

    for y in sorted_years:
        year_id = y.get("id") or y.get("Id")
        if not year_id:
            continue
        offs = api.request_json(
            "GET",
            "/offerings",
            query={"akademikYilId": year_id, "bolumId": bolum_id},
        )
        if isinstance(offs, list) and len(offs) > 0:
            return year_id

    # Hic offering yoksa onceki davranisa geri don
    return pick_year_id(years, None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Program yeterliliklerini API ile uygular")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API veya site URL. Ornek: https://yzdd.gop.edu.tr/dpks")
    parser.add_argument("--live", action="store_true", help="Canli ortami otomatik secer")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--mapping-json", default=DEFAULT_MAPPING)
    parser.add_argument("--report-json", default=DEFAULT_REPORT)
    parser.add_argument("--bolum-id", default=None)
    parser.add_argument("--bolum-keyword", default=TARGET_BOLUM_KEYWORD)
    parser.add_argument("--year-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    mapping_path = Path(args.mapping_json)
    if not mapping_path.exists():
        raise SystemExit(f"Mapping dosyasi bulunamadi: {mapping_path}")

    with mapping_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    ders_to_pys = mapping.get("ders_program_yeterlilikleri", {})
    ders_to_scores = mapping.get("ders_program_yeterlilik_puanlari", {})

    resolved_base_url = resolve_base_url(args.base_url, args.live)
    api = ApiClient(resolved_base_url)

    login = api.request_json(
        "POST",
        "/auth/login",
        {"email": args.email, "password": args.password},
    )
    token = login.get("token")
    if not token:
        raise ApiError("Login token alinmadi")
    api.token = token

    bolum_id = args.bolum_id
    if not bolum_id:
        bolumler = api.request_json("GET", "/bolumler")
        bolum_id = pick_bolum_id(bolumler, args.bolum_keyword)

    years = api.request_json("GET", "/academic-years")
    year_id = pick_year_with_offerings(api, years, bolum_id, args.year_id)

    offerings = api.request_json(
        "GET",
        "/offerings",
        query={"akademikYilId": year_id, "bolumId": bolum_id},
    )

    offering_by_code: dict[str, str] = {}
    for off in offerings:
        ders = off.get("Ders") or off.get("ders") or {}
        code = (ders.get("Kod") or ders.get("kod") or "").strip().upper()
        off_id = off.get("Id") or off.get("id")
        if code and off_id and code not in offering_by_code:
            offering_by_code[code] = off_id

    all_outcomes = api.request_json(
        "GET",
        "/outcomes",
        query={"akademikYilId": year_id},
    )

    outcome_by_kod: dict[str, dict[str, Any]] = {}
    for o in all_outcomes:
        kod = (o.get("kod") or o.get("Kod") or "").strip().upper()
        if not kod:
            continue
        existing = outcome_by_kod.get(kod)
        this_bolum = o.get("bolumId") or o.get("BolumId")
        # Bolume ait outcome varsa onu tercih et
        if existing is None:
            outcome_by_kod[kod] = o
        else:
            existing_bolum = existing.get("bolumId") or existing.get("BolumId")
            if existing_bolum != bolum_id and this_bolum == bolum_id:
                outcome_by_kod[kod] = o

    needed_py_codes: set[str] = set()
    for course_code, py_list in ders_to_pys.items():
        cc = str(course_code).upper()
        if cc not in offering_by_code:
            continue
        for raw in py_list:
            py = normalize_py_code(str(raw))
            if py:
                needed_py_codes.add(py)

    created_outcomes: list[str] = []
    for py in sorted(needed_py_codes, key=lambda x: int(x[2:])):
        if py in outcome_by_kod:
            continue
        if args.dry_run:
            continue

        create_payload = {
            "akademikYilId": year_id,
            "kod": py,
            "aciklama": f"{py} program yeterliligi",
            "bolumId": bolum_id,
        }
        created = api.request_json("POST", "/outcomes", create_payload)
        created_outcomes.append(py)
        # CreatedAtAction return shape is OutcomeDto
        outcome_by_kod[py] = created

    changes: list[dict[str, Any]] = []
    skipped_courses: list[str] = []

    for course_code, py_list in ders_to_pys.items():
        cc = str(course_code).upper()
        offering_id = offering_by_code.get(cc)
        if not offering_id:
            skipped_courses.append(cc)
            continue

        score_map = ders_to_scores.get(course_code) or ders_to_scores.get(cc) or {}

        for raw in py_list:
            py = normalize_py_code(str(raw))
            if not py:
                continue

            outcome = outcome_by_kod.get(py)
            if not outcome:
                continue

            outcome_id = outcome.get("id") or outcome.get("Id")
            if not outcome_id:
                continue

            # Once puan haritasina bak
            raw_score = score_map.get(py)
            if raw_score is None:
                # Eski format P1/PY1 farki icin fallback
                raw_score = score_map.get(py.replace("PY", "P"))

            score = parse_score(raw_score)
            if score is None:
                # PY listesinde var ama puan yoksa varsayilan 1
                score = 1

            changes.append(
                {
                    "dersSunumuId": offering_id,
                    "programYeterligiId": outcome_id,
                    "deger": score,
                }
            )

    report = {
        "base_url": resolved_base_url,
        "bolum_id": bolum_id,
        "year_id": year_id,
        "dry_run": args.dry_run,
        "offering_count": len(offering_by_code),
        "mapping_course_count": len(ders_to_pys),
        "applied_change_count": len(changes),
        "created_outcomes": created_outcomes,
        "skipped_courses_not_found_in_offerings": sorted(set(skipped_courses)),
    }

    if not args.dry_run and changes:
        # Tek seferde gonder
        resp = api.request_json("PUT", "/matrix/bulk", {"degisiklikler": changes})
        report["bulk_update_response"] = resp

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Rapor yazildi: {report_path}")
    print(f"Bolum ID: {bolum_id}")
    print(f"Akademik Yil ID: {year_id}")
    print(f"Toplam degisiklik: {len(changes)}")
    if args.dry_run:
        print("Dry-run: API'ye yazma yapilmadi.")
    else:
        print("API guncelleme tamamlandi.")


if __name__ == "__main__":
    try:
        main()
    except ApiError as ex:
        print(f"HATA: {ex}", file=sys.stderr)
        sys.exit(1)
