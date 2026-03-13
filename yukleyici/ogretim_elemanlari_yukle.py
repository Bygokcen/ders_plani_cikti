"""
ogretim_elemanlari_yukle.py
-----------------------------
ogretim_elemanlari.json dosyasındaki öğretim elemanlarını
API üzerinden ilgili bölüme ekler.

Yapılan işlemler:
  1. API'ye giriş yap (admin@gop.edu.tr / admin123)
    2. Fakülte listesinde hedef fakülteyi bul (yoksa oluştur)
    3. Bölüm listesinde hedef bölümü bul (yoksa oluştur)
  4. Her öğretim elemanı için:
       a. Fotoğrafı Docker container'a kopyala
       b. POST /dpks-api/faculty ile elemanı oluştur
  5. Özet tablo yaz

Gereksinim: requests  →  pip install requests
"""

import json
import os
import subprocess
import requests
import re
import argparse
from pathlib import Path

from api_runtime import resolve_base_url, login as api_login, auth_headers, is_local_api

# ─── Ayarlar ──────────────────────────────────────────────────────────────

CONTAINER     = 'dpks_backend'
CONTAINER_DIR = '/app/wwwroot/uploads/faculty'
DEFAULT_JSON_PATH = str(Path(__file__).resolve().parents[1] / 'ogretim_elemanlari.json')
DEFAULT_FOTO_DIR = str(Path(__file__).resolve().parents[1] / 'ogretim_elemanlari_foto')

DEFAULT_FAKULTE_AD = 'Mimarlık ve Mühendislik Fakültesi'
DEFAULT_FAKULTE_KOD = 'MMF'
DEFAULT_BOLUM_AD = 'Bilgisayar Mühendisliği'
DEFAULT_BOLUM_KOD = 'BILMUH'

# ─── Yardımcılar ──────────────────────────────────────────────────────────

def headers(token):
    return auth_headers(token)


def get_or_create_fakulte(base_url, token, verify_ssl, fakulte_ad, fakulte_kod):
    r = requests.get(f'{base_url}/fakulteler', headers=headers(token), timeout=20, verify=verify_ssl)
    r.raise_for_status()
    for f in r.json():
        ad = f.get('ad', '') or ''
        kod = f.get('kod', '') or ''
        if ad.strip().lower() == fakulte_ad.strip().lower() or kod.strip().upper() == fakulte_kod.strip().upper():
            print(f'✅ Fakülte bulundu: {f["ad"]} ({f["id"][:8]}…)')
            return f['id']

    # Yoksa oluştur
    r2 = requests.post(f'{base_url}/fakulteler',
                       headers=headers(token),
                       json={'ad': fakulte_ad, 'kod': fakulte_kod, 'renk': '#1e40af'},
                       timeout=20,
                       verify=verify_ssl)
    r2.raise_for_status()
    fid = r2.json()['id']
    print(f'🆕 Fakülte oluşturuldu: {fakulte_ad} ({fid[:8]}…)')
    return fid


def get_or_create_bolum(base_url, token, fakulte_id, verify_ssl, bolum_ad, bolum_kod):
    r = requests.get(f'{base_url}/bolumler', headers=headers(token), timeout=20, verify=verify_ssl)
    r.raise_for_status()
    for b in r.json():
        ad = b.get('ad', '') or ''
        kod = b.get('kod', '') or ''
        if ad.strip().lower() == bolum_ad.strip().lower() or kod.strip().upper() == bolum_kod.strip().upper():
            print(f'✅ Bölüm bulundu: {b["ad"]} ({b["id"][:8]}…)')
            return b['id']

    # Yoksa oluştur
    r2 = requests.post(f'{base_url}/bolumler',
                       headers=headers(token),
                       json={
                           'ad': bolum_ad,
                           'kod': bolum_kod,
                           'fakulteId': fakulte_id,
                           'varsayilanSinifSayisi': 4
                       },
                       timeout=20,
                       verify=verify_ssl)
    r2.raise_for_status()
    bid = r2.json()['id']
    print(f'🆕 Bölüm oluşturuldu: {bolum_ad} ({bid[:8]}…)')
    return bid


def get_existing_faculty(base_url, token, bolum_id, verify_ssl):
    """Zaten kayıtlı e-postalar kümesini döndürür (pagination destekli)."""
    epostalar = set()
    page = 1
    while True:
        r = requests.get(f'{base_url}/faculty', headers=headers(token),
                 params={'page': page, 'limit': 100, 'bolumId': bolum_id}, timeout=20, verify=verify_ssl)
        if not r.ok:
            break
        data = r.json()
        # API liste ya da sayfalı obje döndürebilir
        items = data if isinstance(data, list) else data.get('data', data.get('items', []))
        if not items:
            break
        epostalar.update(f['eposta'].lower() for f in items if f.get('eposta'))
        if isinstance(data, list):
            break  # sayfalama yok, liste döndü
        pagination = data.get('pagination', {})
        if page >= pagination.get('totalPages', 1):
            break
        page += 1
    return epostalar


def copy_photo_to_docker(local_path, filename, container_name=CONTAINER):
    """Fotoğrafı Docker container'a kopyalar, /uploads/faculty/ altına."""
    # Önce hedef klasörü oluştur
    subprocess.run(
        ['docker', 'exec', container_name, 'mkdir', '-p', CONTAINER_DIR],
        capture_output=True
    )
    dest = f'{container_name}:{CONTAINER_DIR}/{filename}'
    result = subprocess.run(
        ['docker', 'cp', local_path, dest],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f'    ⚠️  Fotoğraf kopyalanamadı: {result.stderr.strip()}')
        return None
    return f'/uploads/faculty/{filename}'


def upload_photo_via_api(base_url, token, local_path, verify_ssl):
    with open(local_path, 'rb') as f:
        files = {'file': (os.path.basename(local_path), f, 'application/octet-stream')}
        r = requests.post(
            f'{base_url}/upload/photo',
            headers=auth_headers(token, with_json=False),
            files=files,
            timeout=30,
            verify=verify_ssl,
        )
    if not r.ok:
        return None
    return (r.json() or {}).get('path')


def parse_name(ad_soyad):
    """
    'Prof. Dr. Remzi YILDIRIM' → {'unvan': 'Prof. Dr.', 'ad': 'Remzi', 'soyad': 'YILDIRIM'}
    """
    unvan_pattern = re.compile(
        r'^((?:(?:Prof|Doç|Dr|Öğr|Arş|Gör|Yrd)\.?\s*)+(?:Üyesi|Dr\.?)?\s*)',
        re.IGNORECASE
    )
    m = unvan_pattern.match(ad_soyad.strip())
    unvan = m.group(1).strip() if m else None
    rest  = ad_soyad[m.end():].strip() if m else ad_soyad.strip()
    parts = rest.split()
    ad    = parts[0] if parts else rest
    soyad = ' '.join(parts[1:]) if len(parts) > 1 else None
    return {'unvan': unvan, 'ad': ad, 'soyad': soyad}


def create_faculty(base_url, token, eleman, bolum_id, foto_yolu, verify_ssl):
    p = parse_name(eleman['ad_soyad'])
    payload = {
        'ad': p['ad'],
        'soyad': p['soyad'],
        'unvan': p['unvan'],
        'eposta': eleman['eposta'],
        'icHat': eleman.get('ic_hat'),
        'calismaAlanlari': eleman.get('calisma_alanlari'),
        'fotografYolu': foto_yolu,
        'bolumId': bolum_id,
        'createUserAccount': True,
        'odaNo': None,
    }
    r = requests.post(f'{base_url}/faculty',
                      headers=headers(token),
                      json=payload,
                      timeout=20,
                      verify=verify_ssl)
    return r


def main():
    parser = argparse.ArgumentParser(description='Ogretim elemanlarini API uzerinden yukler')
    parser.add_argument('--base-url', default=None, help='API veya site URL. Ornek: https://yzdd.gop.edu.tr/dpks')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--email', default=os.getenv('DPKS_ADMIN_EMAIL', 'admin@gop.edu.tr'))
    parser.add_argument('--password', default=os.getenv('DPKS_ADMIN_PASSWORD', 'admin123'))
    parser.add_argument('--json-path', default=DEFAULT_JSON_PATH)
    parser.add_argument('--foto-dir', default=DEFAULT_FOTO_DIR)
    parser.add_argument('--photo-mode', choices=['auto', 'api', 'docker', 'none'], default='auto')
    parser.add_argument('--container', default=CONTAINER)
    parser.add_argument('--fakulte-ad', default=DEFAULT_FAKULTE_AD)
    parser.add_argument('--fakulte-kod', default=DEFAULT_FAKULTE_KOD)
    parser.add_argument('--bolum-ad', default=DEFAULT_BOLUM_AD)
    parser.add_argument('--bolum-kod', default=DEFAULT_BOLUM_KOD)
    parser.add_argument('--insecure', action='store_true', help='SSL sertifika dogrulamasini kapatir')
    args = parser.parse_args()

    base_url = resolve_base_url(args.base_url, args.live)
    verify_ssl = not args.insecure

    if args.photo_mode == 'auto':
        photo_mode = 'docker' if is_local_api(base_url) else 'api'
    else:
        photo_mode = args.photo_mode

    # ── 1. JSON Yükle
    with open(args.json_path, encoding='utf-8') as f:
        data = json.load(f)
    print(f'📄 {len(data)} öğretim elemanı JSON\'dan okundu.\n')
    print(f'🌐 API: {base_url}')
    print(f'🖼️  Foto mod: {photo_mode}\n')

    # ── 2. Giriş
    token = api_login(base_url, args.email, args.password, verify_ssl=verify_ssl)
    print(f'✅ Giriş başarılı: {args.email}')

    # ── 3. Fakülte / Bölüm
    fakulte_id = get_or_create_fakulte(base_url, token, verify_ssl, args.fakulte_ad, args.fakulte_kod)
    bolum_id   = get_or_create_bolum(base_url, token, fakulte_id, verify_ssl, args.bolum_ad, args.bolum_kod)
    print()

    # ── 4. Mevcut elemanları çek
    existing = get_existing_faculty(base_url, token, bolum_id, verify_ssl)

    # ── 5. Elemanları ekle
    results = []
    for slug, eleman in data.items():
        ad_soyad = eleman.get('ad_soyad', slug)
        eposta   = eleman.get('eposta', '')

        if eposta.lower() in existing:
            print(f'⏭️  Zaten var, atlandı : {ad_soyad}')
            results.append((ad_soyad, 'ATLANDI', ''))
            continue

        # Fotoğraf kopyala
        foto_yolu  = None
        foto_field = eleman.get('foto')
        if foto_field:
            fname      = os.path.basename(foto_field)
            local_path = os.path.join(args.foto_dir, fname)
            if os.path.exists(local_path):
                if photo_mode == 'api':
                    foto_yolu = upload_photo_via_api(base_url, token, local_path, verify_ssl)
                elif photo_mode == 'docker':
                    foto_yolu = copy_photo_to_docker(local_path, fname, args.container)
                elif photo_mode == 'none':
                    foto_yolu = None

        # API çağrısı
        r = create_faculty(base_url, token, eleman, bolum_id, foto_yolu, verify_ssl)
        if r.status_code in (200, 201):
            print(f'✅ Eklendi : {ad_soyad} (foto={foto_yolu or "yok"})')
            results.append((ad_soyad, 'EKLENDI', foto_yolu or ''))
        else:
            msg = r.json().get('error') or r.json().get('message') or r.text[:80]
            print(f'❌ HATA    : {ad_soyad} → {msg}')
            results.append((ad_soyad, 'HATA', msg))

    # ── 6. Özet
    print('\n── Özet ──────────────────────────────────────────')
    eklendi  = sum(1 for _, s, _ in results if s == 'EKLENDI')
    atlanan  = sum(1 for _, s, _ in results if s == 'ATLANDI')
    hatali   = sum(1 for _, s, _ in results if s == 'HATA')
    print(f'Eklendi : {eklendi}')
    print(f'Atlandı : {atlanan} (zaten mevcut)')
    print(f'Hata    : {hatali}')
    if hatali:
        print('\nHatalı kayıtlar:')
        for ad, s, msg in results:
            if s == 'HATA':
                print(f'  • {ad}: {msg}')


if __name__ == '__main__':
    main()
