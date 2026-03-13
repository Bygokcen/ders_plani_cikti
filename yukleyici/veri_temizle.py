"""
Yukleyici scriptleriyle olusan verileri API uzerinden temizler.

Temizlenen temel alanlar (bolum + akademik yil kapsaminda):
  - Danisman atamalari
  - Ders programi kayitlari
  - Program yeterlilikleri (outcomes)
  - Ders sunumlari (silinince ders plani + haftalik plan + matris de cascade temizlenir)
  - Dersler
  - Ogretim elemanlari (ilgili user hesaplariyla birlikte)

Opsiyonel:
  - Bolum kaydi
  - Fakulte kaydi
"""

from __future__ import annotations

import argparse
import os
from typing import Iterable

import requests

from api_runtime import (
    auth_headers,
    find_bolum_id,
    login as api_login,
    resolve_base_url,
)


def get_json(url: str, headers: dict, params: dict | None, verify_ssl: bool) -> list | dict:
    r = requests.get(url, headers=headers, params=params, timeout=30, verify=verify_ssl)
    r.raise_for_status()
    return r.json()


def delete_items(
    base_url: str,
    headers: dict,
    endpoint: str,
    ids: Iterable[str],
    verify_ssl: bool,
    dry_run: bool,
    label: str,
) -> tuple[int, int]:
    ok_count = 0
    fail_count = 0

    for item_id in ids:
        if dry_run:
            print(f"  [DRY-RUN] DELETE {endpoint}/{item_id}")
            ok_count += 1
            continue

        r = requests.delete(
            f"{base_url}{endpoint}/{item_id}",
            headers=headers,
            timeout=30,
            verify=verify_ssl,
        )

        if r.status_code in (200, 202, 204):
            ok_count += 1
        elif r.status_code == 404:
            # Zaten silinmis olabilir; temizleme senaryosunda sorun degil.
            ok_count += 1
        else:
            fail_count += 1
            print(f"  ❌ {label} silinemedi ({item_id}): HTTP {r.status_code} {r.text[:180]}")

    return ok_count, fail_count


def pick_year_id(base_url: str, headers: dict, explicit_year_id: str | None, verify_ssl: bool) -> str:
    if explicit_year_id:
        return explicit_year_id

    years = get_json(f"{base_url}/academic-years", headers, None, verify_ssl)
    if not isinstance(years, list) or not years:
        raise RuntimeError("Akademik yil bulunamadi. --year-id parametresiyle manuel verin.")

    years = sorted(
        years,
        key=lambda y: str(y.get("yilKodu") or y.get("YilKodu") or ""),
        reverse=True,
    )
    picked = years[0].get("id") or years[0].get("Id")
    if not picked:
        raise RuntimeError("Akademik yil id okunamadi. --year-id parametresiyle manuel verin.")
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description="Yukleme sonrasi verileri API uzerinden temizler")
    parser.add_argument("--base-url", default=None, help="API veya site URL. Ornek: https://yzdd.gop.edu.tr/dpks")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--email", default=os.getenv("DPKS_ADMIN_EMAIL", "admin@gop.edu.tr"))
    parser.add_argument("--password", default=os.getenv("DPKS_ADMIN_PASSWORD", "admin123"))
    parser.add_argument("--bolum-id", default=None)
    parser.add_argument("--bolum-keyword", default="bilgisayar")
    parser.add_argument("--year-id", default=None)
    parser.add_argument("--delete-bolum", action="store_true", help="Temizlik sonunda bolumu da sil")
    parser.add_argument("--delete-fakulte", action="store_true", help="Temizlik sonunda fakulteyi de sil")
    parser.add_argument("--dry-run", action="store_true", help="Silmeden sadece neleri silecegini yazdir")
    parser.add_argument("--insecure", action="store_true", help="SSL sertifika dogrulamasini kapatir")
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url, args.live)
    verify_ssl = not args.insecure

    token = api_login(base_url, args.email, args.password, verify_ssl=verify_ssl)
    headers = auth_headers(token)

    bolum_id = args.bolum_id or find_bolum_id(base_url, token, args.bolum_keyword, verify_ssl=verify_ssl)
    yil_id = pick_year_id(base_url, headers, args.year_id, verify_ssl)

    print(f"🌐 API: {base_url}")
    print(f"✅ Bolum ID: {bolum_id}")
    print(f"✅ Akademik Yil ID: {yil_id}")
    print(f"🧪 Mod: {'DRY-RUN' if args.dry_run else 'GERCEK SILME'}")

    # 1) Danisman atamalari (yil + bolum)
    advisors = get_json(
        f"{base_url}/danismanlar/{yil_id}",
        headers,
        {"bolumId": bolum_id},
        verify_ssl,
    )
    advisor_ids = [(x.get("id") or x.get("Id")) for x in advisors if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Danisman atamalari: {len(advisor_ids)}")
    ok, fail = delete_items(base_url, headers, "/danismanlar", advisor_ids, verify_ssl, args.dry_run, "Danisman")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 2) Ders programi (yil + bolum)
    programs = get_json(
        f"{base_url}/ders-programi/{yil_id}",
        headers,
        {"bolumId": bolum_id},
        verify_ssl,
    )
    program_ids = [(x.get("id") or x.get("Id")) for x in programs if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Ders programi kaydi: {len(program_ids)}")
    ok, fail = delete_items(base_url, headers, "/ders-programi", program_ids, verify_ssl, args.dry_run, "DersProgrami")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 3) Program yeterlilikleri (yil + bolum)
    outcomes = get_json(
        f"{base_url}/outcomes",
        headers,
        {"akademikYilId": yil_id, "bolumId": bolum_id},
        verify_ssl,
    )
    outcome_ids = [(x.get("id") or x.get("Id")) for x in outcomes if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Program yeterliligi: {len(outcome_ids)}")
    ok, fail = delete_items(base_url, headers, "/outcomes", outcome_ids, verify_ssl, args.dry_run, "ProgramYeterliligi")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 4) Offerings (yil + bolum)
    offerings = get_json(
        f"{base_url}/offerings",
        headers,
        {"akademikYilId": yil_id, "bolumId": bolum_id},
        verify_ssl,
    )
    offering_ids = [(x.get("id") or x.get("Id")) for x in offerings if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Ders sunumu: {len(offering_ids)}")
    ok, fail = delete_items(base_url, headers, "/offerings", offering_ids, verify_ssl, args.dry_run, "DersSunumu")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 5) Dersler (bolum)
    courses = get_json(
        f"{base_url}/courses",
        headers,
        {"bolumId": bolum_id},
        verify_ssl,
    )
    course_ids = [(x.get("id") or x.get("Id")) for x in courses if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Ders: {len(course_ids)}")
    ok, fail = delete_items(base_url, headers, "/courses", course_ids, verify_ssl, args.dry_run, "Ders")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 6) Ogretim elemanlari (bolum)
    faculty = get_json(
        f"{base_url}/faculty",
        headers,
        {"bolumId": bolum_id},
        verify_ssl,
    )
    faculty_ids = [(x.get("id") or x.get("Id")) for x in faculty if (x.get("id") or x.get("Id"))]
    print(f"\n🧹 Ogretim elemani: {len(faculty_ids)}")
    ok, fail = delete_items(base_url, headers, "/faculty", faculty_ids, verify_ssl, args.dry_run, "OgretimElemani")
    print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    # 7) Opsiyonel bolum/fakulte silme
    if args.delete_bolum:
        print("\n🧹 Bolum silme")
        ok, fail = delete_items(base_url, headers, "/bolumler", [bolum_id], verify_ssl, args.dry_run, "Bolum")
        print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")

    if args.delete_fakulte:
        bolum_info = get_json(f"{base_url}/bolumler/{bolum_id}", headers, None, verify_ssl)
        fakulte_id = bolum_info.get("fakulteId") or bolum_info.get("FakulteId")
        if fakulte_id:
            print("\n🧹 Fakulte silme")
            ok, fail = delete_items(base_url, headers, "/fakulteler", [fakulte_id], verify_ssl, args.dry_run, "Fakulte")
            print(f"  ✅ Silinen: {ok} | ❌ Hata: {fail}")
        else:
            print("\n⚠️ Fakulte ID okunamadi, fakulte silme atlandi.")

    print("\n✅ Temizlik islemi tamamlandi.")


if __name__ == "__main__":
    main()