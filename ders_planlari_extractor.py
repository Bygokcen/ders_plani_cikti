#!/usr/bin/env python3
"""
BILMUH 2025-26 Ders Planları Çıkarıcı
======================================
Kaynak: Program_Kılavuzu_BILMUH2025-26_19022026.docx
Çıktı : ders_planlari.json
        ders_gorselleri/<DERS_KODU>/soru_N.{png|jpeg|emf}

Özellikler:
  - Öğretim üyesi, oda, ofis saati, e-posta, ders zamanı, derslik
  - Dersin amacı
  - Konu ve ilgili kazanımlar (sarı arka plan = konu başlığı)
  - 1–14. hafta ders konuları + ilgili program yeterliliği
  - Sınav tarihleri (ara, dönem sonu, bütünleme)
  - Değerlendirme
  - Örnek sorular (OMML matematik → LaTeX $...$, resimler → dosyaya kaydedildi)
  - Kaynak kitap, yardımcı kaynaklar

Tarih: 2026-03-11
"""

import docx
import json
import re
import os

from lxml import etree

# ─── Sabitler ──────────────────────────────────────────────────────────────

DOCX_PATH = '/Users/gokcen/Downloads/Program_Kılavuzu_BILMUH2025-26_19022026.docx'
JSON_OUT  = '/Users/gokcen/DPK/ders_planlari.json'
IMG_BASE  = '/Users/gokcen/DPK/ders_gorselleri'

WNS  = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M    = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
DRAW = '{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}'
A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
EMB  = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

# ─── OMML → LaTeX dönüştürücü ─────────────────────────────────────────────

NARY_MAP = {
    '∫': r'\int',    '∑': r'\sum',   '∏': r'\prod',
    '∮': r'\oint',   '∬': r'\iint',  '∭': r'\iiint',
    '⋃': r'\bigcup', '⋂': r'\bigcap',
    '⋁': r'\bigvee', '⋀': r'\bigwedge',
    '':  r'\int',    # chr val eksik olduğunda integral varsayılanı
}

FUNC_MAP = {
    'sin': r'\sin',  'cos': r'\cos',  'tan': r'\tan',
    'cot': r'\cot',  'sec': r'\sec',  'csc': r'\csc',
    'arcsin': r'\arcsin', 'arccos': r'\arccos', 'arctan': r'\arctan',
    'sinh': r'\sinh', 'cosh': r'\cosh', 'tanh': r'\tanh',
    'log': r'\log',  'ln': r'\ln',   'exp': r'\exp',
    'lim': r'\lim',  'max': r'\max', 'min': r'\min',
    'det': r'\det',  'gcd': r'\gcd',
}

def omml_to_latex(elem):
    """OMML elementini özyinelemeli olarak LaTeX dizgesine çevirir."""
    tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag

    if tag == 'r':
        t_elem = elem.find(f'{M}t')
        return t_elem.text or '' if t_elem is not None else ''

    if tag == 't':
        return elem.text or ''

    children_latex = [omml_to_latex(c) for c in elem]

    if tag == 'f':
        num_e = elem.find(f'{M}num')
        den_e = elem.find(f'{M}den')
        num = omml_to_latex(num_e) if num_e is not None else '?'
        den = omml_to_latex(den_e) if den_e is not None else '?'
        return rf'\frac{{{num}}}{{{den}}}'

    if tag == 'sSup':
        base_e = elem.find(f'{M}e')
        sup_e  = elem.find(f'{M}sup')
        return f'{{{omml_to_latex(base_e) if base_e is not None else ""}}}^{{{omml_to_latex(sup_e) if sup_e is not None else ""}}}'

    if tag == 'sSub':
        base_e = elem.find(f'{M}e')
        sub_e  = elem.find(f'{M}sub')
        return f'{{{omml_to_latex(base_e) if base_e is not None else ""}}}_{{{omml_to_latex(sub_e) if sub_e is not None else ""}}}'

    if tag == 'sSubSup':
        base_e = elem.find(f'{M}e')
        sub_e  = elem.find(f'{M}sub')
        sup_e  = elem.find(f'{M}sup')
        base = omml_to_latex(base_e) if base_e is not None else ''
        sub  = omml_to_latex(sub_e)  if sub_e  is not None else ''
        sup  = omml_to_latex(sup_e)  if sup_e  is not None else ''
        return f'{{{base}}}_{{{sub}}}^{{{sup}}}'

    if tag == 'rad':
        deg_e  = elem.find(f'{M}deg')
        base_e = elem.find(f'{M}e')
        base = omml_to_latex(base_e) if base_e is not None else ''
        if deg_e is not None:
            deg = omml_to_latex(deg_e)
            if deg.strip():
                return rf'\sqrt[{deg}]{{{base}}}'
        return rf'\sqrt{{{base}}}'

    if tag == 'nary':
        pr      = elem.find(f'{M}naryPr')
        chr_e   = pr.find(f'{M}chr') if pr is not None else None
        chr_val = chr_e.get(f'{M}val', '∫') if chr_e is not None else '∫'
        op      = NARY_MAP.get(chr_val, rf'\{chr_val}')
        sub_e   = elem.find(f'{M}sub')
        sup_e   = elem.find(f'{M}sup')
        body_e  = elem.find(f'{M}e')
        sub_s   = ('_{' + omml_to_latex(sub_e)  + '}') if sub_e  is not None else ''
        sup_s   = ('^{' + omml_to_latex(sup_e)  + '}') if sup_e  is not None else ''
        body_s  = omml_to_latex(body_e) if body_e is not None else ''
        return f'{op}{sub_s}{sup_s}{{{body_s}}}'

    if tag == 'd':
        pr    = elem.find(f'{M}dPr')
        beg   = '('
        end   = ')'
        if pr is not None:
            beg_e = pr.find(f'{M}begChr')
            end_e = pr.find(f'{M}endChr')
            if beg_e is not None: beg = beg_e.get(f'{M}val', '(')
            if end_e is not None: end = end_e.get(f'{M}val', ')')
        lb = {'(': r'\left(', '[': r'\left[',  '|': r'\left|',  '{': r'\left\{',  '': ''}.get(beg, beg)
        rb = {')': r'\right)',']': r'\right]', '|': r'\right|', '}': r'\right\}', '': ''}.get(end, end)
        inner = ','.join(omml_to_latex(e) for e in elem.findall(f'{M}e'))
        return f'{lb}{inner}{rb}'

    if tag == 'func':
        fname_e = elem.find(f'{M}fName')
        body_e  = elem.find(f'{M}e')
        fname   = omml_to_latex(fname_e).strip() if fname_e is not None else ''
        fn      = FUNC_MAP.get(fname, fname)
        body    = omml_to_latex(body_e) if body_e is not None else ''
        return f'{fn}{{{body}}}'

    if tag == 'limLow':
        base_e = elem.find(f'{M}e')
        lim_e  = elem.find(f'{M}lim')
        return f'{{{omml_to_latex(base_e) if base_e is not None else ""}}}_{{{omml_to_latex(lim_e) if lim_e is not None else ""}}}'

    if tag == 'limUpp':
        base_e = elem.find(f'{M}e')
        lim_e  = elem.find(f'{M}lim')
        return f'{{{omml_to_latex(base_e) if base_e is not None else ""}}}^{{{omml_to_latex(lim_e) if lim_e is not None else ""}}}'

    if tag == 'acc':
        pr     = elem.find(f'{M}accPr')
        chr_e  = pr.find(f'{M}chr') if pr is not None else None
        chr_v  = chr_e.get(f'{M}val', '̂') if chr_e is not None else '̂'
        body_e = elem.find(f'{M}e')
        body   = omml_to_latex(body_e) if body_e is not None else ''
        acc_map = {'̂': r'\hat', '́': r'\acute', '̃': r'\tilde',
                   '̄':  r'\bar', '̈': r'\ddot',  '̣': r'\dot'}
        return rf'{acc_map.get(chr_v, r"\hat")}{{{body}}}'

    if tag == 'm':
        rows_l = []
        for mr in elem.findall(f'{M}mr'):
            cells = [omml_to_latex(me) for me in mr.findall(f'{M}e')]
            rows_l.append(' & '.join(cells))
        return rf'\begin{{matrix}}{r" \\ ".join(rows_l)}\end{{matrix}}'

    # Şeffaf konteyner etiketleri — çocukları doğrudan birleştir
    if tag in ('oMath', 'oMathPara', 'e', 'num', 'den', 'base',
               'sup', 'sub', 'deg', 'lim', 'fName', 'box',
               'groupChr', 'sSubSupPr', 'sSupPr', 'sSubPr',
               'radPr', 'fPr', 'dPr', 'naryPr', 'funcPr',
               'limLowPr', 'limUppPr', 'accPr', 'mPr', 'ctrlPr'):
        return ''.join(children_latex)

    return ''.join(children_latex)


def cell_tc_to_rich_text(tc):
    """
    Bir tablo hücresinin (tc XML elemanı) içeriğini zengin metin olarak döner.
    - Normal metin: olduğu gibi
    - m:oMath inline: $...$
    - m:oMathPara display: $$...$$
    """
    parts = []
    for para in tc.findall(f'.//{WNS}p'):
        para_parts = []
        for child in para:
            ctag = child.tag.split('}')[-1]
            if ctag == 'r':
                t = child.find(f'{WNS}t')
                if t is not None and t.text:
                    para_parts.append(t.text)
            elif ctag == 'oMath':
                latex = omml_to_latex(child).strip()
                if latex:
                    para_parts.append(f'${latex}$')
            elif ctag == 'oMathPara':
                for om in child.findall(f'{M}oMath'):
                    latex = omml_to_latex(om).strip()
                    if latex:
                        para_parts.append(f'$${latex}$$')
        line = ''.join(para_parts).strip()
        if line:
            parts.append(line)
    return '\n'.join(parts)


# ─── Resim çıkarıcı ───────────────────────────────────────────────────────

def extract_images(tc, doc_part, course_code, img_base):
    """
    Hücreden tüm gömülü görselleri çıkarıp diske yazar.
    Döndürür: proje köküne göre göreli yol listesi.
    """
    saved = []
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
            out_dir   = os.path.join(img_base, course_code)
            os.makedirs(out_dir, exist_ok=True)
            fname = f'soru_{len(saved)+1}.{ext}'
            fpath = os.path.join(out_dir, fname)
            with open(fpath, 'wb') as f:
                f.write(img_bytes)
            saved.append(fpath.replace('/Users/gokcen/DPK/', ''))
        except Exception as e:
            saved.append(f'[hata: {e}]')
    return saved


# ─── Tablo ayrıştırıcılar ─────────────────────────────────────────────────

def text_of(elem):
    return ''.join(t.text or '' for t in elem.iter(f'{WNS}t')).strip()


def is_yellow_cell(cell):
    tcpr = cell._tc.find(f'{WNS}tcPr')
    if tcpr is not None:
        shd = tcpr.find(f'{WNS}shd')
        if shd is not None:
            return shd.get(f'{WNS}fill', '').upper() in ('FFFF00', 'FFFF01', 'FFF200', 'FFFF33')
    return False


def _unique_cells(row):
    """Yatay merge ile kopyalanmış hücreleri düşürür; benzersiz _tc'leri döner.

    python-docx, birleştirilmiş hücrelerde row.cells içinde aynı _tc nesnesini
    birden fazla index'te döndürür.  Bu fonksiyon her _tc'yi yalnızca bir kez
    listeler; böylece [key, key_merge, value, value_merge] → [key, value] olur.
    """
    seen: set = set()
    unique = []
    for cell in row.cells:
        cid = id(cell._tc)
        if cid not in seen:
            seen.add(cid)
            unique.append(cell)
    return unique


# Konu/Kazanım bölüm başlıkları — birden fazla yazım biçimi var
_KK_LABELS = ('Konu ve İlgili Kazanımlar', 'Konu ile İlgili Kazanımlar')


def _add_kk_value(value, value_cell, result, current_topic):
    """Bir konu/kazanım değerini sonuç listesine ekler; güncel topic'i döner."""
    if is_yellow_cell(value_cell):          # sarı arka plan = konu başlığı
        current_topic = {'konu': value, 'kazanimlar': []}
        result['konu_ve_kazanimlar'].append(current_topic)
    else:
        if current_topic is not None:
            current_topic['kazanimlar'].append(value)
        else:
            current_topic = {'konu': '', 'kazanimlar': [value]}
            result['konu_ve_kazanimlar'].append(current_topic)
    return current_topic


def parse_info_table(tbl):
    """İlk tablo: öğretim üyesi bilgileri + amaç + konu/kazanımlar."""
    result = {
        'ogretim_uyesi': '', 'oda_numarasi': '', 'ofis_saati': '',
        'eposta': '', 'ders_zamani': '', 'derslik': '',
        'dersin_amaci': '', 'konu_ve_kazanimlar': []
    }
    current_topic = None
    in_kk_section = False  # dikey merge devam satırlarını izlemek için
    for row in tbl.rows:
        ucells = _unique_cells(row)        # yatay merge kopyalarını düşür
        if len(ucells) < 2:
            continue
        key        = ucells[0].text.strip()
        value_cell = ucells[1]
        value      = value_cell.text.strip()

        if   key == 'Öğretim Üyesi':               result['ogretim_uyesi'] = value
        elif key == 'Oda Numarası':                 result['oda_numarasi']  = value
        elif key == 'Ofis Saati':                   result['ofis_saati']    = value
        elif key == 'E-posta':                      result['eposta']        = value
        elif key == 'Ders Zamanı':                  result['ders_zamani']   = value
        elif key == 'Derslik':                      result['derslik']       = value
        elif key == 'Dersin Amacı':                 result['dersin_amaci']  = value
        elif key in _KK_LABELS:
            in_kk_section = True
            if not value:
                continue                 # boş başlık satırı — sadece bayrağı set et
            current_topic = _add_kk_value(value, value_cell, result, current_topic)
        elif key == '' and in_kk_section:
            # Dikey merge devam satırı: içerik son benzersiz hücrede
            cont_cell  = ucells[-1]
            cont_value = cont_cell.text.strip()
            if not cont_value:
                continue
            current_topic = _add_kk_value(cont_value, cont_cell, result, current_topic)
        elif key:                               # bilinen başka bir alan → KK bölümü bitti
            in_kk_section = False
    return result


def parse_weekly_table(tbl, course_code, doc_part, img_base):
    """İkinci tablo: haftalık plan + değerlendirme + örnek sorular + kaynaklar."""
    result = {
        'haftalik_plan': [], 'sinav_tarihleri': [],
        'degerlendirme': '', 'ornek_sorular': '',
        'ornek_sorular_gorseller': [],
        'kaynak_kitap': '', 'yardimci_kaynaklar': ''
    }
    in_schedule  = False
    week_counter = 0      # tarih-format haftalık planlar için otomatik sayaç
    EXAMS = ('Ara Sınav', 'Dönem Sonu Sınavı', 'Bütünleme Sınavı',
             'Mazeret Sınavı', 'Final Sınavı', 'Vize Sınavı')
    SKIP_KEYS = {'Değerlendirme', 'Örnek Sorular', 'Kaynak Kitap',
                 'Yardımcı Kaynaklar ve Okuma Listesi', 'Hafta-Tarih'}

    for tr in tbl._tbl.findall(f'{WNS}tr'):
        tcs = tr.findall(f'{WNS}tc')
        if not tcs:
            continue
        key = text_of(tcs[0])
        vtc = tcs[2] if len(tcs) >= 3 else (tcs[1] if len(tcs) >= 2 else None)
        get_val = lambda: text_of(vtc) if vtc is not None else ''

        if key == 'Hafta-Tarih':
            in_schedule = True
            continue
        if key == 'Değerlendirme':
            in_schedule = False
            result['degerlendirme'] = get_val()
            continue
        if key == 'Örnek Sorular':
            if vtc is not None:
                result['ornek_sorular']           = cell_tc_to_rich_text(vtc)
                result['ornek_sorular_gorseller'] = extract_images(vtc, doc_part, course_code, img_base)
            continue
        if key == 'Kaynak Kitap':
            result['kaynak_kitap'] = get_val()
            continue
        if key == 'Yardımcı Kaynaklar ve Okuma Listesi':
            result['yardimci_kaynaklar'] = get_val()
            continue

        if in_schedule and len(tcs) >= 2:
            if key.strip().isdigit():
                # Standart format: [hafta, tarih, ders, PY]
                hafta       = int(key.strip())
                content_idx = 2
            elif key and key not in SKIP_KEYS:
                # Tarih-format: [tarih, ders, PY]  veya  [tarih, '', ders, PY]
                # İlk boş olmayan hücreyi içerik olarak al
                week_counter += 1
                hafta        = week_counter
                content_idx  = 1
                for ci in range(1, len(tcs)):
                    if text_of(tcs[ci]).strip():
                        content_idx = ci
                        break
            else:
                # Boş key: sınav satırı gibi — sadece sınav kontrolü yap
                hafta       = None
                content_idx = 2

            ders = text_of(tcs[content_idx]) if len(tcs) > content_idx else ''
            pyet = (text_of(tcs[content_idx + 1])
                    if len(tcs) > content_idx + 1 else '')

            if hafta is not None:
                if ders and not any(ex in ders for ex in EXAMS):
                    result['haftalik_plan'].append({
                        'hafta': hafta,
                        'ders_konusu': ders,
                        'program_yeterliligi': pyet
                    })
                elif ders and any(ex in ders for ex in EXAMS):
                    result['sinav_tarihleri'].append(ders)
            elif ders and any(ex in ders for ex in EXAMS):
                result['sinav_tarihleri'].append(ders)

    return result


# ─── Ana çıkarım döngüsü ──────────────────────────────────────────────────

def main():
    doc      = docx.Document(DOCX_PATH)
    body     = doc.element.body
    children = list(body)
    tables   = doc.tables

    elem_to_tbl = {}
    ti = 0
    for i, c in enumerate(children):
        if c.tag.split('}')[-1] == 'tbl':
            elem_to_tbl[i] = ti
            ti += 1

    os.makedirs(IMG_BASE, exist_ok=True)
    courses = {}

    i = 0
    while i < len(children):
        child = children[i]
        if child.tag.split('}')[-1] != 'p':
            i += 1
            continue

        style_elem = child.find(f'.//{WNS}pStyle')
        style = style_elem.get(f'{WNS}val') if style_elem is not None else 'Normal'

        if style == 'Heading3':
            heading = text_of(child)
            if heading:
                m2 = re.match(r'^([A-Z]+)\s*(\d+)\s*(.*)', heading.strip())
                if m2:
                    code = m2.group(1) + m2.group(2)
                    name = m2.group(3).strip()
                else:
                    parts = heading.strip().split()
                    code  = parts[0] if parts else '?'
                    name  = ' '.join(parts[1:]) if len(parts) > 1 else ''

                tbls = []
                j = i + 1
                while j < len(children):
                    c = children[j]
                    ct = c.tag.split('}')[-1]
                    if ct == 'tbl':
                        ti2 = elem_to_tbl.get(j)
                        if ti2 is not None:
                            tbls.append(tables[ti2])
                    elif ct == 'p':
                        s2 = c.find(f'.//{WNS}pStyle')
                        if s2 is not None and s2.get(f'{WNS}val') in ('Heading1', 'Heading2', 'Heading3'):
                            break
                    j += 1

                entry = {'ders_adi': name}
                if tbls:
                    entry.update(parse_info_table(tbls[0]))
                if len(tbls) >= 2:
                    entry.update(parse_weekly_table(tbls[1], code, doc.part, IMG_BASE))
                elif len(tbls) == 1:
                    w = parse_weekly_table(tbls[0], code, doc.part, IMG_BASE)
                    if w['haftalik_plan'] or w['degerlendirme']:
                        entry.update(w)

                courses[code] = entry

        i += 1

    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)

    print(f"Toplam ders: {len(courses)}")
    print(f"JSON: {JSON_OUT}")
    img_count = sum(
        len(os.listdir(os.path.join(IMG_BASE, d)))
        for d in os.listdir(IMG_BASE)
        if os.path.isdir(os.path.join(IMG_BASE, d))
    )
    print(f"Kaydedilen görsel: {img_count} dosya ({IMG_BASE})")
    math_courses = [code for code, c in courses.items() if '$' in c.get('ornek_sorular', '')]
    img_courses  = [code for code, c in courses.items() if c.get('ornek_sorular_gorseller')]
    print(f"LaTeX math içeren: {math_courses}")
    print(f"Görsel içeren    : {img_courses}")


if __name__ == '__main__':
    main()
