"""
Tam doldurulmus ders planlarini is akisindan gecmis gibi toplu onaylar.

Akis:
1) Admin ile giris
2) Ilgili yil+bolum syllabus listesini al
3) ValidationErrors bos olan planlari sec
4) DRAFT/REJECTED planlari, ilgili akademisyen hesabiyla SUBMIT et (varsayilan sifre ile)
5) SUBMITTED olanlari admin ile APPROVE et

Not:
- Syllabus submit endpoint'i admin'e kapali oldugu icin submit adiminda akademisyen
  hesabina ihtiyac vardir.
- Varsayilan akademisyen sifresi proje koduna gore: Dpks2025!
"""

from __future__ import annotations

import argparse
import os

import requests

from api_runtime import auth_headers, find_bolum_id, resolve_base_url


def login(base_url: str, email: str, password: str, verify_ssl: bool) -> str | None:
    r = requests.post(
        f"{base_url}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
        verify=verify_ssl,
    )
    if not r.ok:
        return None
    return (r.json() or {}).get("token")


def pick_year_id(base_url: str, token: str, explicit_year_id: str | None, verify_ssl: bool) -> str:
    if explicit_year_id:
        return explicit_year_id

    r = requests.get(f"{base_url}/academic-years", headers=auth_headers(token), timeout=30, verify=verify_ssl)
    r.raise_for_status()
    years = r.json() or []
    if not years:
        raise RuntimeError("Akademik yil bulunamadi")

    years = sorted(years, key=lambda y: str(y.get("yilKodu") or y.get("YilKodu") or ""), reverse=True)
    picked = years[0].get("id") or years[0].get("Id")
    if not picked:
        raise RuntimeError("Akademik yil ID bulunamadi")
    return picked


def main() -> None:
    parser = argparse.ArgumentParser(description="Tam ders planlarini toplu onaya alir")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--admin-email", default=os.getenv("DPKS_ADMIN_EMAIL", "admin@gop.edu.tr"))
    parser.add_argument("--admin-password", default=os.getenv("DPKS_ADMIN_PASSWORD", "admin123"))
    parser.add_argument("--academic-password", default="Dpks2025!")
    parser.add_argument("--bolum-id", default=None)
    parser.add_argument("--bolum-keyword", default="bilgisayar")
    parser.add_argument("--year-id", default=None)
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url, args.live)
    verify_ssl = not args.insecure

    admin_token = login(base_url, args.admin_email, args.admin_password, verify_ssl)
    if not admin_token:
        raise RuntimeError("Admin girisi basarisiz")

    headers_admin = auth_headers(admin_token)
    bolum_id = args.bolum_id or find_bolum_id(base_url, admin_token, args.bolum_keyword, verify_ssl=verify_ssl)
    yil_id = pick_year_id(base_url, admin_token, args.year_id, verify_ssl)

    offerings_r = requests.get(
        f"{base_url}/offerings",
        params={"akademikYilId": yil_id, "bolumId": bolum_id},
        headers=headers_admin,
        timeout=40,
        verify=verify_ssl,
    )
    offerings_r.raise_for_status()
    offerings = offerings_r.json() or []

    instructor_map: dict[str, list[str]] = {}
    for item in offerings:
        offering_id = item.get("id") or item.get("Id")
        instructors = item.get("OgretimElemanlari") or item.get("ogretimElemanlari") or []
        emails = [(x.get("Eposta") or x.get("eposta") or "").strip().lower() for x in instructors]
        instructor_map[offering_id] = [e for e in emails if e]

    status_r = requests.get(
        f"{base_url}/syllabus/year/{yil_id}/status",
        headers=headers_admin,
        timeout=40,
        verify=verify_ssl,
    )
    status_r.raise_for_status()
    statuses = status_r.json() or []

    candidates: list[tuple[str, str, str]] = []
    for row in statuses:
        syllabus_id = row["id"]
        offering_id = row["dersSunumuId"]
        current_status = str(row.get("status") or "").upper()

        if current_status == "APPROVED":
            continue

        detail_r = requests.get(
            f"{base_url}/syllabus/{offering_id}",
            headers=headers_admin,
            timeout=40,
            verify=verify_ssl,
        )
        if not detail_r.ok:
            continue

        detail = detail_r.json() or {}
        errors = detail.get("validationErrors") or detail.get("ValidationErrors") or []
        if errors:
            continue

        candidates.append((syllabus_id, offering_id, current_status))

    academic_tokens: dict[str, str | None] = {}
    submit_ok = 0
    submit_fail: list[tuple[str, str]] = []
    approve_ok = 0
    approve_fail: list[tuple[str, str]] = []

    for syllabus_id, offering_id, current_status in candidates:
        status_now = current_status

        if status_now in {"DRAFT", "REJECTED"}:
            submitted = False
            fail_reason = ""
            for email in instructor_map.get(offering_id, []):
                if email not in academic_tokens:
                    academic_tokens[email] = login(base_url, email, args.academic_password, verify_ssl)

                token = academic_tokens[email]
                if not token:
                    continue

                submit_r = requests.post(
                    f"{base_url}/syllabus/submit/{syllabus_id}",
                    headers=auth_headers(token),
                    timeout=30,
                    verify=verify_ssl,
                )
                if submit_r.status_code == 200:
                    submit_ok += 1
                    submitted = True
                    status_now = "SUBMITTED"
                    break

                fail_reason = f"{email} -> {submit_r.status_code}"

            if not submitted:
                submit_fail.append((syllabus_id, fail_reason or "akademisyen login/yetki yok"))
                continue

        if status_now == "SUBMITTED":
            approve_r = requests.post(
                f"{base_url}/syllabus/approve/{syllabus_id}",
                headers=headers_admin,
                timeout=30,
                verify=verify_ssl,
            )
            if approve_r.status_code == 200:
                approve_ok += 1
            else:
                approve_fail.append((syllabus_id, f"{approve_r.status_code} {approve_r.text[:120]}"))

    print("--- TOPLU DERS PLANI ONAY OZETI ---")
    print(f"API: {base_url}")
    print(f"Bolum ID: {bolum_id}")
    print(f"Akademik Yil ID: {yil_id}")
    print(f"Tam plan adayi: {len(candidates)}")
    print(f"Submit basarili: {submit_ok}")
    print(f"Submit atlanan/hata: {len(submit_fail)}")
    print(f"Approve basarili: {approve_ok}")
    print(f"Approve hata: {len(approve_fail)}")

    if submit_fail:
        print("\nSubmit hatalari (ilk 20):")
        for sid, msg in submit_fail[:20]:
            print(f"  - {sid}: {msg}")

    if approve_fail:
        print("\nApprove hatalari (ilk 20):")
        for sid, msg in approve_fail[:20]:
            print(f"  - {sid}: {msg}")


if __name__ == "__main__":
    main()