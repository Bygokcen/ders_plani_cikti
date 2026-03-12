"""
ogretim_elemanlari.py
----------------------
Program_Kılavuzu_BILMUH2025-26_19022026.docx dosyasından
tüm öğretim elemanlarını fotoğraflarıyla birlikte çıkarır.

Çıktı:
  ogretim_elemanlari.json          -- tüm elemanların verisi
  ogretim_elemanlari_foto/<ad>.ext -- fotoğraf dosyaları
"""

import docx
import json
import os
import re

from lxml import etree

DOCX     = '/Users/gokcen/Downloads/Program_Kılavuzu_BILMUH2025-26_19022026.docx'
JSON_OUT = '/Users/gokcen/DPK/ders_planlari_cikti/ogretim_elemanlari.json'
IMG_BASE = '/Users/gokcen/DPK/ders_planlari_cikti/ogretim_elemanlari_foto'

WNS  = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
EMB  = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
DRAW = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'


def slugify(name):
    """Ad-soyad'dan dosya adı üret."""
    name = name.strip()
    # Unvanları at (Prof. Dr., Doç. Dr., Dr. Öğr. Üyesi, Arş. Gör. Dr. vb.)
    name = re.sub(
        r'^(Prof\.|Doç\.|Dr\.|Öğr\.|Arş\.|Gör\.|Üyesi|Yrd\.)\s*', '', name
    ).strip()
    name = re.sub(r'\s+', '_', name)
    # Türkçe karakter dönüşümü
    tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosucgiosu')
    name = name.translate(tr_map)
    name = re.sub(r'[^A-Za-z0-9_-]', '', name)
    return name or 'ogretim_elemani'


def parse_cell_text(cell):
    """
    Hücre metnini satır satır okuyup alanlara ayırır.
    Yapı:
      Satır 1 : Ad Soyad (+ unvan baştaysa)
      Satır N : email@gop.edu.tr
      Satır N : İç Hat: XXXX
      Satır N : Çalışma Alanları: ...
    """
    paragraphs = [p.text.strip() for p in cell.paragraphs if p.text.strip()]

    ad_soyad       = ''
    eposta         = ''
    ic_hat         = ''
    calisma_alanlari = ''
    extra_lines    = []

    for line in paragraphs:
        if '@gop.edu.tr' in line or '@' in line:
            eposta = line.strip()
        elif line.startswith('İç Hat'):
            ic_hat = re.sub(r'İç Hat\s*[:\-]?\s*', '', line).strip()
        elif 'Çalışma Alanları' in line or 'Çalismus' in line:
            calisma_alanlari = re.sub(r'Çalışma Alanları\s*[:\-]?\s*', '', line).strip()
        elif not ad_soyad:
            ad_soyad = line
        else:
            extra_lines.append(line)

    # Bazen ad ve e-posta aynı satırda olabilir
    if not ad_soyad and eposta:
        ad_soyad = eposta

    return {
        'ad_soyad': ad_soyad,
        'eposta': eposta,
        'ic_hat': ic_hat,
        'calisma_alanlari': calisma_alanlari,
    }


def extract_photo(cell, doc_part, slug, img_base):
    """Hücredeki ilk gömülü resmi slug.ext adıyla diske yazar."""
    tc = cell._tc
    drawings = tc.findall(f'.//{DRAW}inline') + tc.findall(f'.//{DRAW}anchor')
    for drawing in drawings:
        blip = drawing.find(f'.//{{{A_NS}}}blip')
        if blip is None:
            continue
        r_embed = blip.get(f'{{{EMB}}}embed')
        if not r_embed:
            continue
        try:
            img_part  = doc_part.rels[r_embed].target_part
            img_bytes = img_part.blob
            ext       = img_part.partname.split('.')[-1].lower()
            os.makedirs(img_base, exist_ok=True)
            fname = f'{slug}.{ext}'
            fpath = os.path.join(img_base, fname)
            with open(fpath, 'wb') as f:
                f.write(img_bytes)
            # Proje köküne göreli yol döndür
            return fpath.replace('/Users/gokcen/DPK/', '')
        except Exception as e:
            return f'[hata: {e}]'
    return None


def main():
    doc  = docx.Document(DOCX)
    # Tablo 4 (0-indexli) = BM bölümü akademik kadro tablosu
    tbl  = doc.tables[4]

    results  = {}
    counters = {}  # aynı slug varsa numara ekle

    for row in tbl.rows:
        if not row.cells:
            continue
        cell = row.cells[0]
        info = parse_cell_text(cell)

        if not info['ad_soyad']:
            continue

        slug = slugify(info['ad_soyad'])
        # Çakışma varsa numara ekle
        if slug in counters:
            counters[slug] += 1
            slug = f'{slug}_{counters[slug]}'
        else:
            counters[slug] = 1

        foto = extract_photo(cell, doc.part, slug, IMG_BASE)
        info['foto'] = foto

        results[slug] = info
        print(f"  {info['ad_soyad']:50s} -> foto: {foto}")

    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nToplam: {len(results)} öğretim elemanı")
    print(f"JSON  : {JSON_OUT}")
    foto_count = sum(1 for v in results.values() if v['foto'] and not v['foto'].startswith('['))
    print(f"Fotoğraf: {foto_count} dosya ({IMG_BASE})")


if __name__ == '__main__':
    main()
