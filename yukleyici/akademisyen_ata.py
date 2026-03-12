"""
ders_planlari.json'daki akademisyen atamalarını API'ye yükler.
Strateji:
  1. Önce e-posta ile eşleştir (API'deki faculty listesine karşı)
  2. Bulunamazsa isim normalizasyonuyla eşleştir
  3. O da bulunamazsa o dersi atla ve raporla
"""
import argparse
import json
import os
import re
import unicodedata
from pathlib import Path

import requests

from api_runtime import resolve_base_url, login as api_login, auth_headers, find_bolum_id, pick_year_id_with_offerings

DEFAULT_JSON = str(Path(__file__).resolve().parents[1] / 'ders_planlari.json')

def normalize(s: str) -> str:
    """Türkçe karakterleri ASCII'ye çevir, küçük harf yap, unvanı temizle."""
    unvanlar = [
        r'prof\.\s*dr\.', r'doç\.\s*dr\.', r'dr\.\s*öğr\.\s*üyesi',
        r'dr\.öğr\.\s*üyesi', r'dr\.öğr\.üyesi', r'öğr\.\s*gör\.\s*dr\.',
        r'öğr\.gör\.dr\.', r'öğr\.\s*gör\.', r'arş\.\s*gör\.\s*dr\.',
        r'arş\.gör\.dr\.', r'arş\.\s*gör\.', r'doç\.\s*dr\.üyesi'
    ]
    s2 = s.lower().strip()
    for pat in unvanlar:
        s2 = re.sub(pat, '', s2, flags=re.IGNORECASE)
    # Türkçe → ASCII
    tr = str.maketrans('çğışöüÇĞİŞÖÜ', 'cgisouCGISOu')
    s2 = s2.translate(tr)
    # Unicode normalize
    s2 = unicodedata.normalize('NFD', s2)
    s2 = ''.join(c for c in s2 if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s2).strip()

def find_faculty_id(email_to_id: dict, name_to_id: dict, email: str, name_hint: str) -> str | None:
    """Önce e-posta, sonra isim ile ara; bulamazsa None."""
    # E-posta ile ara
    fid = email_to_id.get(email.lower().strip())
    if fid:
        return fid
    # Normalize isim ile ara
    norm = normalize(name_hint)
    fid = name_to_id.get(norm)
    if fid:
        return fid
    # Kısmi isim araması: API isimlerinden biri norm içinde mi?
    for api_norm, fid2 in name_to_id.items():
        if api_norm and api_norm in norm:
            return fid2
    return None

def main():
    parser = argparse.ArgumentParser(description='Ders offering akademisyen atamalarini API uzerinden yapar')
    parser.add_argument('--base-url', default=None, help='API veya site URL. Ornek: https://yzdd.gop.edu.tr/dpks')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--email', default=os.getenv('DPKS_ADMIN_EMAIL', 'admin@gop.edu.tr'))
    parser.add_argument('--password', default=os.getenv('DPKS_ADMIN_PASSWORD', 'admin123'))
    parser.add_argument('--json-path', default=DEFAULT_JSON)
    parser.add_argument('--bolum-id', default=None)
    parser.add_argument('--bolum-keyword', default='bilgisayar')
    parser.add_argument('--year-id', default=None)
    parser.add_argument('--insecure', action='store_true', help='SSL sertifika dogrulamasini kapatir')
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url, args.live)
    verify_ssl = not args.insecure

    token = api_login(base_url, args.email, args.password, verify_ssl=verify_ssl)
    hdrs = auth_headers(token)

    bolum_id = args.bolum_id or find_bolum_id(base_url, token, args.bolum_keyword, verify_ssl=verify_ssl)
    yil_id = pick_year_id_with_offerings(base_url, token, bolum_id, args.year_id, verify_ssl=verify_ssl)

    faculty = requests.get(f'{base_url}/faculty', headers=hdrs, timeout=30, verify=verify_ssl).json()
    email_to_id = {f['eposta'].lower(): f['id'] for f in faculty if f.get('eposta')}

    name_to_id = {}
    for f in faculty:
        full = f"{f['ad']} {f['soyad']}" if f.get('soyad') else f['ad']
        name_to_id[normalize(full)] = f['id']

    offerings_resp = requests.get(
        f'{base_url}/offerings',
        params={'akademikYilId': yil_id, 'bolumId': bolum_id},
        headers=hdrs,
        timeout=30,
        verify=verify_ssl,
    )
    offerings = offerings_resp.json()
    kod_to_offering = {}
    for o in offerings:
        ders = o.get('ders') or o.get('Ders') or {}
        kod = ders.get('kod') or ders.get('Kod')
        oid = o.get('id') or o.get('Id')
        if kod and oid:
            kod_to_offering[str(kod).strip().upper()] = oid

    print(f'🌐 API: {base_url}')
    print(f'✅ Bolum ID: {bolum_id}')
    print(f'✅ Akademik Yil ID: {yil_id}')
    print(f'Toplam offering: {len(offerings)}')

    with open(args.json_path, encoding='utf-8') as f:
        ders_planlari = json.load(f)

    atandi = 0
    atlamaListesi = []

    for ders_kodu, ders in ders_planlari.items():
    ogr_str  = ders.get('ogretim_uyesi', '').strip()
    eposta_str = ders.get('eposta', '').strip()

    if not ogr_str or ogr_str == 'Öğretim Üyesi':
        continue  # atanacak kişi belli değil

    # Offering var mı?
    offering_id = kod_to_offering.get(ders_kodu.upper())
    if not offering_id:
        atlamaListesi.append(f'  ⚠️  {ders_kodu}: offering yok (akademik yılda bulunmuyor)')
        continue

    # Birden fazla akademisyen olabilir (virgülle ayrılmış)
    isimler = [i.strip() for i in ogr_str.split(',')]
    epostalar = [e.strip() for e in eposta_str.split(',')]

    faculty_ids = []
    for i, isim in enumerate(isimler):
        ep = epostalar[i] if i < len(epostalar) else ''
        fid = find_faculty_id(email_to_id, name_to_id, ep, isim)
        if fid:
            if fid not in faculty_ids:
                faculty_ids.append(fid)
        else:
            atlamaListesi.append(f'  ❓  {ders_kodu}: "{isim}" ({ep}) bulunamadı')

    if not faculty_ids:
        atlamaListesi.append(f'  ⛔  {ders_kodu}: hiç akademisyen eşleşmedi')
        continue

    # PUT /offerings/{id}/instructors
    put_r = requests.put(
        f'{base_url}/offerings/{offering_id}/instructors',
        headers=hdrs,
        json={'ogretimElemaniIds': faculty_ids},
        timeout=30,
        verify=verify_ssl,
    )
    if put_r.status_code == 200:
        isim_kisa = ', '.join(isimler)
        print(f'  ✅  {ders_kodu}: {isim_kisa}')
        atandi += 1
    else:
        print(f'  ❌  {ders_kodu}: HTTP {put_r.status_code} - {put_r.text}')

# ── 6. Özet ───────────────────────────────────────────────────────────────
    print(f'\n--- ÖZET ---')
    print(f'✅ Atanan: {atandi} ders')
    if atlamaListesi:
        print(f'⚠️  Notlar ({len(atlamaListesi)}):')
        for msg in atlamaListesi:
            print(msg)


if __name__ == '__main__':
    main()
