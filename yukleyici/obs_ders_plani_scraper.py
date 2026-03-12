"""
obs_ders_plani_scraper.py
--------------------------
https://obs.gop.edu.tr — Bologna modülündeki bölüm ders planını JSON'a aktarır.

Çıktı: obs_ders_plani.json
"""

import json
import re
import warnings

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings('ignore', message='Unverified HTTPS')

URL      = 'https://obs.gop.edu.tr/oibs//bologna/progCourses.aspx?lang=tr&curSunit=2001547'
JSON_OUT = '/Users/gokcen/DPK/ders_planlari_cikti/obs_ders_plani.json'

# Yarıyıl → (sınıf, dönem) eşlemesi
YARIYIL_MAP = {
    1: (1, 'Güz'),  2: (1, 'Bahar'),
    3: (2, 'Güz'),  4: (2, 'Bahar'),
    5: (3, 'Güz'),  6: (3, 'Bahar'),
    7: (4, 'Güz'),  8: (4, 'Bahar'),
}


def parse_tul(tul_str):
    """'3+1+0' → {'teorik':3, 'uygulamali':1, 'lab':0}"""
    parts = tul_str.split('+')
    try:
        teorik      = int(parts[0]) if len(parts) > 0 else 0
        uygulamali  = int(parts[1]) if len(parts) > 1 else 0
        lab         = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        teorik = uygulamali = lab = 0
    return teorik, uygulamali, lab


def main():
    print(f'İndiriliyor: {URL}')
    r = requests.get(URL, timeout=20, verify=False)
    r.encoding = 'utf-8'
    soup = BeautifulSoup(r.text, 'html.parser')

    # Sayfa başlığından bölüm adını al
    tables = soup.find_all('table')
    bolum_ad = ''
    if tables:
        ilk = tables[0].get_text(' ', strip=True)
        m = re.search(r'Bilgisayar Mühendisliği', ilk)
        if m:
            bolum_ad = 'Bilgisayar Mühendisliği'

    # Ana tablo (index 1)
    tbl  = tables[1]
    rows = tbl.find_all('tr')

    dersler      = []
    current_yariyil   = None
    current_sinif     = None
    current_donem     = None
    current_grup_kod  = None   # "Seçmeli 1-1" gibi grup başlığı
    current_grup_adi  = None
    current_grup_akts = None
    current_grup_secenekler = []

    def flush_grup():
        """Açık seçmeli grubu tamamla."""
        nonlocal current_grup_kod, current_grup_adi, current_grup_akts, current_grup_secenekler
        if current_grup_kod:
            dersler.append({
                'sinif'           : current_sinif,
                'donem'           : current_donem,
                'yariyil'         : current_yariyil,
                'ders_kodu'       : current_grup_kod,
                'ders_adi'        : current_grup_adi,
                'teorik'          : None,
                'uygulamali'      : None,
                'lab'             : None,
                'tipi'            : 'Seçmeli (Grup)',
                'akts'            : current_grup_akts,
                'ogretim_sekli'   : None,
                'grup_secenekler' : current_grup_secenekler,
            })
        current_grup_kod       = None
        current_grup_adi       = None
        current_grup_akts      = None
        current_grup_secenekler = []

    for row in rows:
        cells = row.find_all(['th', 'td'])
        vals  = [c.get_text(strip=True) for c in cells]

        # Boş satır veya sütun başlığı satırı atla
        if len(vals) < 2:
            continue
        if vals[1] == 'Ders Kodu':
            continue
        if not any(vals):
            continue

        # ── Yarıyıl başlığı: "1.Yarıyıl Ders Planı"
        yariyil_match = re.search(r'(\d+)\.Yarıyıl', vals[2] if len(vals) > 2 else '')
        if yariyil_match:
            flush_grup()
            current_yariyil = int(yariyil_match.group(1))
            current_sinif, current_donem = YARIYIL_MAP.get(current_yariyil, (None, None))
            print(f'  → {current_yariyil}.Yarıyıl | {current_sinif}.Sınıf | {current_donem}')
            continue

        if current_yariyil is None:
            continue

        # ── Toplam AKTS satırı — atla
        if 'Toplam AKTS' in vals:
            continue

        # Sütunları al
        # [0]=boş [1]=ders_kodu [2]=ders_adi [3]=T+U+L [4]=tip [5]=akts [6]=grup_adedi [7]=ogretim
        kod          = vals[1] if len(vals) > 1 else ''
        ad           = vals[2] if len(vals) > 2 else ''
        tul_str      = vals[3] if len(vals) > 3 else '0+0+0'
        tip          = vals[4] if len(vals) > 4 else ''
        akts_str     = vals[5] if len(vals) > 5 else ''
        grup_adedi   = vals[6] if len(vals) > 6 else ''
        ogr_sekli    = vals[7] if len(vals) > 7 else ''

        if not kod and not ad:
            continue

        try:
            akts = int(akts_str) if akts_str.isdigit() else None
        except Exception:
            akts = None

        teorik, uygulamali, lab = parse_tul(tul_str)

        # ── Seçmeli Grup başlığı mı? (Grup Ders Adedi dolu)
        if grup_adedi.strip():
            flush_grup()
            current_grup_kod        = kod
            current_grup_adi        = ad
            current_grup_akts       = akts
            current_grup_secenekler = []
            continue

        # ── Aktif seçmeli grubun alt seçeneği
        if current_grup_kod:
            current_grup_secenekler.append({
                'ders_kodu'   : kod,
                'ders_adi'    : ad,
                'teorik'      : teorik,
                'uygulamali'  : uygulamali,
                'lab'         : lab,
                'akts'        : akts,
                'ogretim_sekli': ogr_sekli,
            })
            continue

        # ── Normal zorunlu/seçmeli ders
        flush_grup()
        dersler.append({
            'sinif'           : current_sinif,
            'donem'           : current_donem,
            'yariyil'         : current_yariyil,
            'ders_kodu'       : kod,
            'ders_adi'        : ad,
            'teorik'          : teorik,
            'uygulamali'      : uygulamali,
            'lab'             : lab,
            'tipi'            : 'Zorunlu' if 'Zorunlu' in tip else ('Seçmeli' if 'Seçmeli' in tip else tip),
            'akts'            : akts,
            'ogretim_sekli'   : ogr_sekli,
            'grup_secenekler' : None,
        })

    flush_grup()  # son grubu kapat

    # ── Çıktı yap
    result = {
        'bolum'      : bolum_ad,
        'kaynak_url' : URL,
        'toplam_ders': len(dersler),
        'dersler'    : dersler,
    }

    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # ── Özet
    yariyil_ozet = {}
    for d in dersler:
        key = (d['yariyil'], d['sinif'], d['donem'])
        yariyil_ozet.setdefault(key, 0)
        yariyil_ozet[key] += 1

    print(f'\n{"─"*55}')
    print(f'Bölüm  : {bolum_ad}')
    print(f'Toplam : {len(dersler)} ders kaydı\n')
    print(f'  {"Yarıyıl":<12} {"Sınıf":<8} {"Dönem":<8} {"Kayıt":<6}')
    for (y, s, d), cnt in sorted(yariyil_ozet.items()):
        print(f'  {y}.Yarıyıl   {s}.Sınıf  {d:<8} {cnt}')
    print(f'\nJSON: {JSON_OUT}')


if __name__ == '__main__':
    main()
