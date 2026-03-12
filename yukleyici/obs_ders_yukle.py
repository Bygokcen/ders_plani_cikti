"""
obs_ders_yukle.py
------------------
obs_ders_plani.json'daki dersleri Docker projesinin
Bilgisayar Mühendisliği bölümüne API üzerinden ekler.

POST /dpks-api/courses
  { Kod, Ad, AKTS, TeoriSaat, UygulamaSaat, Tur, Dil, Donem, BolumId }

Gereksinim: pip install requests
"""

import json
import argparse
import os
from pathlib import Path
import warnings
import requests
from api_runtime import resolve_base_url, login as api_login, auth_headers, find_bolum_id, pick_year_id_with_offerings

warnings.filterwarnings('ignore')

DEFAULT_JSON = str(Path(__file__).resolve().parents[1] / 'obs_ders_plani.json')


# ── Yardımcılar ────────────────────────────────────────────────────────────

def hdrs(token):
    return auth_headers(token)


def existing_codes(base_url, token, bolum_id, verify_ssl):
    r = requests.get(f'{base_url}/courses?bolumId={bolum_id}', headers=hdrs(token), timeout=20, verify=verify_ssl)
    if not r.ok:
        return set()
    return {c.get('kod', '').strip() for c in r.json()}


def donem_str(d):
    """1→'Güz', 2→'Bahar', ...  (API'nin Donem alanı int)"""
    return d  # API integer dönem bekliyor (1..8)


def main():
    parser = argparse.ArgumentParser(description='OBS derslerini API uzerinden yukler')
    parser.add_argument('--base-url', default=None, help='API veya site URL. Ornek: https://yzdd.gop.edu.tr/dpks')
    parser.add_argument('--live', action='store_true', help='Canli ortami otomatik secer')
    parser.add_argument('--email', default=os.getenv('DPKS_ADMIN_EMAIL', 'admin@gop.edu.tr'))
    parser.add_argument('--password', default=os.getenv('DPKS_ADMIN_PASSWORD', 'admin123'))
    parser.add_argument('--json-path', default=DEFAULT_JSON)
    parser.add_argument('--bolum-keyword', default='bilgisayar')
    parser.add_argument('--year-id', default=None)
    parser.add_argument('--insecure', action='store_true', help='SSL sertifika dogrulamasini kapatir')
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url, args.live)
    verify_ssl = not args.insecure

    # ── Yükle
    with open(args.json_path, encoding='utf-8') as f:
        data = json.load(f)
    dersler = data['dersler']
    print(f'📄 {len(dersler)} ders kaydı okundu.')
    print(f'🌐 API: {base_url}\n')

    token = api_login(base_url, args.email, args.password, verify_ssl=verify_ssl)
    print(f'✅ Giris: {args.email}')

    bolum_id = find_bolum_id(base_url, token, args.bolum_keyword, verify_ssl=verify_ssl)
    print(f'✅ Bolum ID: {bolum_id}')

    yil_id = pick_year_id_with_offerings(base_url, token, bolum_id, args.year_id, verify_ssl=verify_ssl)
    print(f'✅ Akademik Yil ID: {yil_id}')

    mevcut = existing_codes(base_url, token, bolum_id, verify_ssl)
    print(f'ℹ️  Zaten kayıtlı ders kodu sayısı: {len(mevcut)}\n')

    eklendi = 0
    atlandi = 0
    hatali  = 0
    hatalar = []

    for d in dersler:
        kod = d['ders_kodu'].strip()
        ad  = d['ders_adi'].strip()

        # Seçmeli grup başlıkları yüklenmiyor — alt seçenekler ayrıca yükleniyor
        if d['tipi'] == 'Seçmeli (Grup)':
            # Alt seçenekleri yükle
            for sec in (d.get('grup_secenekler') or []):
                skod = sec['ders_kodu'].strip()
                sad  = sec['ders_adi'].strip()
                if skod in mevcut:
                    print(f'⏭️  Atlandı: {skod}')
                    atlandi += 1
                    continue
                payload = {
                    'kod'          : skod,
                    'ad'           : sad,
                    'akts'         : sec.get('akts') or 0,
                    'teoriSaat'    : sec.get('teorik') or 0,
                    'uygulamaSaat' : sec.get('uygulamali') or 0,
                    'tur'          : 'Secmeli',
                    'dil'          : 'Türkçe',
                    'donem'        : d['yariyil'],
                    'bolumId'      : bolum_id,
                    'akademikYilId': yil_id,
                }
                r = requests.post(f'{base_url}/courses', headers=hdrs(token),
                                  json=payload, timeout=20, verify=verify_ssl)
                if r.status_code in (200, 201):
                    print(f'✅ Eklendi: {skod} — {sad[:45]}')
                    mevcut.add(skod)
                    eklendi += 1
                else:
                    msg = (r.json().get('error') or r.json().get('message') or r.text)[:80]
                    print(f'❌ Hata   : {skod} → {msg}')
                    hatali += 1
                    hatalar.append((skod, msg))
            continue

        # Zaten var mı?
        if kod in mevcut:
            print(f'⏭️  Atlandı: {kod}')
            atlandi += 1
            continue

        tur_str = 'Zorunlu' if d['tipi'] == 'Zorunlu' else 'Secmeli'

        payload = {
            'kod'          : kod,
            'ad'           : ad,
            'akts'         : d.get('akts') or 0,
            'teoriSaat'    : d.get('teorik') or 0,
            'uygulamaSaat' : d.get('uygulamali') or 0,
            'tur'          : tur_str,
            'dil'          : 'Türkçe',
            'donem'        : d['yariyil'],
            'bolumId'      : bolum_id,
            'akademikYilId': yil_id,
        }

        r = requests.post(f'{base_url}/courses', headers=hdrs(token),
                  json=payload, timeout=20, verify=verify_ssl)
        if r.status_code in (200, 201):
            print(f'✅ Eklendi: {kod} — {ad[:45]}')
            mevcut.add(kod)
            eklendi += 1
        else:
            try:
                msg = (r.json().get('error') or r.json().get('message') or r.text)[:80]
            except Exception:
                msg = r.text[:80]
            print(f'❌ Hata   : {kod} → {msg}')
            hatali += 1
            hatalar.append((kod, msg))

    print(f'\n{"─"*50}')
    print(f'Eklendi : {eklendi}')
    print(f'Atlandı : {atlandi}  (zaten mevcut)')
    print(f'Hata    : {hatali}')
    if hatalar:
        print('\nHatalı kayıtlar:')
        for kod, msg in hatalar:
            print(f'  • {kod}: {msg}')


if __name__ == '__main__':
    main()
