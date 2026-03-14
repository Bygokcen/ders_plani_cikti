"""
ders_planlari.json → API syllabus yükleyici
  - Admin tokenı kullanır (tüm offering'lere erişim)
  - Her ders için GET → yoksa POST, varsa POST skipla
  - Ardından PUT /weekly ile haftalık planı günceller
  - Veri eksik/uyumsuz dersleri raporlar
"""
import argparse
import json
import os
import re
from pathlib import Path

import requests

from api_runtime import resolve_base_url, login as api_login, auth_headers, find_bolum_id, pick_year_id_with_offerings

DEFAULT_JSON = str(Path(__file__).resolve().parents[1] / 'ders_planlari.json')


def serialize_konu_kazanim(liste: list) -> str:
    """
    [{konu, kazanimlar:[]}] → "1. Konu\n   1.1 Kazanım\n   1.2 Kazanım\n\n2. ..."
    Bu format syllabusHelpers.js parseTopics() ile uyumludur.
    """
    bloklar = []
    for i, item in enumerate(liste, 1):
        konu_baslik = f"{i}. {item.get('konu', '').strip()}"
        kazanim_satirlari = [
            f"   {i}.{j} {k.strip()}"
            for j, k in enumerate(item.get('kazanimlar', []), 1)
        ]
        bloklar.append('\n'.join([konu_baslik] + kazanim_satirlari))
    return '\n\n'.join(bloklar)


GUNLER = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
_GUN_PAT = '|'.join(GUNLER)
_SAAT_RE = re.compile(
    r'(?:(' + _GUN_PAT + r'))?\s*\(?\s*(\d{1,2})[:.]\s*(\d{2})\s*[-–]\s*(\d{1,2})[:.]\s*(\d{2})\s*\)?',
    re.IGNORECASE
)

def parse_ders_zamani(dz_str: str | None, derslik: str | None) -> list:
    """'Cuma(09:30-12:15)' veya 'Pzt 08.30-12.15, Sal 08.30-12.15' → DersSaatBilgisiDto listesi."""
    if not dz_str or dz_str.strip() in ('', 'Ders Zamanı'):
        return []
    sonuc = []
    current_gun = None
    for m in _SAAT_RE.finditer(dz_str):
        gun = m.group(1) or current_gun
        if m.group(1):
            current_gun = m.group(1)
        if gun:  # gun=None ise API validation hatası verir, atla
            sonuc.append({
                'gun': gun,
                'baslangicSaati': f"{int(m.group(2)):02d}:{m.group(3)}",
                'bitisSaati':     f"{int(m.group(4)):02d}:{m.group(5)}",
                'derslik': derslik or ''
            })
    return sonuc


def _pick_exam_labels(sinav_tarihleri: list | None) -> tuple[str, str, str]:
    """Sinav listesinde varsa etiketleri kullan, yoksa varsayilanlari don."""
    ara = 'Ara Sınav'
    final = 'Final Sınavı'
    but = 'Bütünleme Sınavı'

    if not sinav_tarihleri:
        return ara, final, but

    for item in sinav_tarihleri:
        t = str(item or '').strip()
        low = t.lower()
        if not t:
            continue
        if 'ara' in low and 'sınav' in low:
            ara = t
        elif ('dönem sonu' in low or 'final' in low) and 'sınav' in low:
            final = t
        elif 'bütünleme' in low and 'sınav' in low:
            but = t

    return ara, final, but


def build_haftalik(hp_list: list, sinav_tarihleri: list | None = None) -> list:
    """
    [{hafta, ders_konusu, program_yeterliligi}] → WeeklyPlanItemRequest list
    """
    ara_label, final_label, but_label = _pick_exam_labels(sinav_tarihleri)

    rows = []
    for h in hp_list:
        rows.append({
            'hafta': h.get('hafta'),
            'tarihAraligi': None,
            'konu': h.get('ders_konusu', ''),
            'ilgiliPYler': h.get('program_yeterliligi', '') or ''
        })

    def has_topic(keyword: str) -> bool:
        k = keyword.lower()
        return any(k in str(r.get('konu') or '').lower() for r in rows)

    def insert_after_week(week: int, new_items: list[dict]) -> None:
        idx = next((i for i, r in enumerate(rows) if r.get('hafta') == week), None)
        if idx is None:
            rows.extend(new_items)
        else:
            rows[idx + 1:idx + 1] = new_items

    if not has_topic('ara sınav'):
        insert_after_week(8, [{
            'hafta': None,
            'tarihAraligi': None,
            'konu': ara_label,
            'ilgiliPYler': ''
        }])

    final_items = []
    if not has_topic('final') and not has_topic('dönem sonu sınavı'):
        final_items.append({
            'hafta': None,
            'tarihAraligi': None,
            'konu': final_label,
            'ilgiliPYler': ''
        })
    if not has_topic('bütünleme sınavı'):
        final_items.append({
            'hafta': None,
            'tarihAraligi': None,
            'konu': but_label,
            'ilgiliPYler': ''
        })
    if final_items:
        insert_after_week(14, final_items)

    result = []
    for i, r in enumerate(rows, 1):
        result.append({
            'sira': i,
            'hafta': r.get('hafta'),
            'tarihAraligi': r.get('tarihAraligi'),
            'konu': r.get('konu', ''),
            'ilgiliPYler': r.get('ilgiliPYler', '') or ''
        })
    return result


def build_payload(ders_kodu: str, ders: dict, offering_id: str) -> dict:
    """CreateSyllabusRequest / UpdateSyllabusRequest alanlarını doldur."""
    konu_kaz_liste = ders.get('konu_ve_kazanimlar') or []
    konu_kazanim_str = serialize_konu_kazanim(konu_kaz_liste) if konu_kaz_liste else None

    # Kaynaklar: kitap + yardımcı
    kaynak_kitap  = (ders.get('kaynak_kitap') or '').strip()
    yardimci      = (ders.get('yardimci_kaynaklar') or '').strip()
    kaynaklar_str = None
    if kaynak_kitap and yardimci:
        kaynaklar_str = f"Ana Kaynak: {kaynak_kitap}\n\nYardımcı Kaynaklar: {yardimci}"
    elif kaynak_kitap:
        kaynaklar_str = f"Ana Kaynak: {kaynak_kitap}"
    elif yardimci:
        kaynaklar_str = f"Yardımcı Kaynaklar: {yardimci}"

    hp = ders.get('haftalik_plan') or []
    sinav_tarihleri = ders.get('sinav_tarihleri') or []

    # ornek_sorular -> JSON stringified array [ { "text": "...", "image": null } ]
    ornek_sorular_raw = (ders.get('ornek_sorular') or '').strip()
    ornek_sorular_json = None
    if ornek_sorular_raw:
        # Web UI standard format expects an array of objects
        ornek_sorular_json = json.dumps([{"text": ornek_sorular_raw, "answer": "", "image": None, "layout": "full"}])

    return {
        'dersSunumuId': offering_id,
        'amac': ders.get('dersin_amaci') or None,
        'konuKazanim': konu_kazanim_str,
        'olcme': ders.get('degerlendirme') or None,
        'kaynaklar': kaynaklar_str,
        'ornekSorular': ornek_sorular_json,
        'ofisSaati': ders.get('ofis_saati') or None,
        'dersZamani': ders.get('ders_zamani') or None,
        'odaNumarasi': ders.get('oda_numarasi') or None,
        'arasinavTarihi': None,
        'finalTarihi': None,
        'butunlemeTarihi': None,
        'dersSaatleri': parse_ders_zamani(ders.get('ders_zamani'), ders.get('derslik')),
        '_haftalik': build_haftalik(hp, sinav_tarihleri),
    }


def check_missing(ders_kodu: str, ders: dict) -> list[str]:
    """Eksik veya otomatik doldurulamayan alanları döndür."""
    eksikler = []
    if not ders.get('dersin_amaci'):
        eksikler.append('dersin_amaci')
    if not ders.get('konu_ve_kazanimlar'):
        eksikler.append('konu_ve_kazanimlar')
    if not ders.get('haftalik_plan'):
        eksikler.append('haftalik_plan')
    if not ders.get('degerlendirme'):
        eksikler.append('degerlendirme')
    if not ders.get('kaynak_kitap') and not ders.get('yardimci_kaynaklar'):
        eksikler.append('kaynaklar')
    return eksikler


def main():
    parser = argparse.ArgumentParser(description='ders_planlari.json verisini syllabus API uzerine yukler')
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

    offerings = requests.get(
        f'{base_url}/offerings',
        params={'akademikYilId': yil_id, 'bolumId': bolum_id},
        headers=hdrs,
        timeout=30,
        verify=verify_ssl,
    ).json()

    kod_to_offering = {}
    for o in offerings:
        ders = o.get('ders') or o.get('Ders') or {}
        kod = ders.get('kod') or ders.get('Kod')
        oid = o.get('id') or o.get('Id')
        if kod and oid:
            kod_to_offering[str(kod).strip().upper()] = oid

    with open(args.json_path, encoding='utf-8') as f:
        ders_planlari = json.load(f)

    print(f'🌐 API: {base_url}')
    print(f'✅ Bolum ID: {bolum_id}')
    print(f'✅ Akademik Yil ID: {yil_id}')
    print(f'📚 Offering sayisi: {len(kod_to_offering)}')

    # ── Ana döngü ────────────────────────────────────────────────────────────
    yuklenenler = []
    atlananlar = []
    manuel_giris = []

    for ders_kodu, ders in ders_planlari.items():
        ogr_str = ders.get('ogretim_uyesi', '').strip()

        # Bilinmeyen hoca - atla
        if not ogr_str or ogr_str == 'Öğretim Üyesi':
            atlananlar.append(f'  ⏩  {ders_kodu}: "Öğretim Üyesi" — hoca atanmamış')
            continue

        # Offering var mı?
        offering_id = kod_to_offering.get(ders_kodu.upper())
        if not offering_id:
            atlananlar.append(f'  ⚠️  {ders_kodu}: offering bulunamadı (2025-2026 yılında yok)')
            continue

        # Eksik alan analizi
        eksikler = check_missing(ders_kodu, ders)

        # Mevcut ders planını kontrol et
        existing_r = requests.get(f'{base_url}/syllabus/{offering_id}', headers=hdrs, timeout=30, verify=verify_ssl)
        syllabus_exists = existing_r.status_code == 200
        existing_data = existing_r.json() if syllabus_exists else None

        payload = build_payload(ders_kodu, ders, offering_id)
        haftalik = payload.pop('_haftalik')

        if syllabus_exists:
            syllabus_id = existing_data['id']
            # Güncelle
            put_r = requests.put(f'{base_url}/syllabus/{syllabus_id}', headers=hdrs, json=payload, timeout=30, verify=verify_ssl)
            if put_r.status_code != 200:
                print(f'  ❌  {ders_kodu} güncelleme hatası: {put_r.status_code} {put_r.text[:120]}')
                continue
            action = 'GÜNCELLENDİ'
        else:
            # Yeni oluştur
            payload['dersSunumuId'] = offering_id
            post_r = requests.post(f'{base_url}/syllabus', headers=hdrs, json=payload, timeout=30, verify=verify_ssl)
            if post_r.status_code not in (200, 201):
                print(f'  ❌  {ders_kodu} oluşturma hatası: {post_r.status_code} {post_r.text[:120]}')
                continue
            created = post_r.json()
            syllabus_id = created['id']
            action = 'OLUŞTURULDU'

        # Haftalık plan — ayrı endpoint
        if haftalik:
            w_r = requests.put(
                f'{base_url}/syllabus/{syllabus_id}/weekly',
                headers=hdrs,
                json={'haftalikPlan': haftalik},
                timeout=30,
                verify=verify_ssl,
            )
            hafta_durum = f'({len(haftalik)} hafta)' if w_r.status_code == 200 else f'(haftalık HATA {w_r.status_code})'
        else:
            hafta_durum = '(haftalık plan yok)'

        eksik_str = f' ⚠️ EKSİK: {", ".join(eksikler)}' if eksikler else ''
        print(f'  ✅  {ders_kodu} [{action}] {hafta_durum}{eksik_str}')
        yuklenenler.append(ders_kodu)

        if eksikler:
            manuel_giris.append((ders_kodu, ders.get('ders_adi','?'), ogr_str, eksikler))

# ── Özet ─────────────────────────────────────────────────────────────────────
    print(f'\n{"="*60}')
    print(f'ÖZET: {len(yuklenenler)} ders planı yüklendi/güncellendi')

    if atlananlar:
        print(f'\nAtlanan ({len(atlananlar)}):')
        for m in atlananlar:
            print(m)

    if manuel_giris:
        print(f'\n🖊️  EL İLE GİRİŞ GEREKENLER ({len(manuel_giris)} ders):')
        print(f'{"KOD":<12} {"DERS ADI":<45} {"HOCA":<35} EKSİK ALANLAR')
        print('-'*130)
        for kod, ad, hoca, eksikler in manuel_giris:
            print(f'{kod:<12} {ad[:44]:<45} {hoca[:34]:<35} {", ".join(eksikler)}')
    else:
        print('\n✅ Tüm atanmış dersler için ders planı eksiksiz yüklendi.')


if __name__ == '__main__':
    main()
