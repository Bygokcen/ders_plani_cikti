#!/usr/bin/env python3
"""
Ders planı DOCX çıkarıcı
========================
Kaynak: program kılavuzu DOCX dosyası
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

import argparse
import docx
import json
import re
import os
from pathlib import Path

from lxml import etree

# ─── Sabitler ──────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_JSON_OUT = Path(__file__).resolve().with_name('ders_planlari.json')
DEFAULT_IMG_BASE = Path(__file__).resolve().with_name('ders_gorselleri')

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


def find_default_docx() -> Path | None:
    candidates = sorted(ROOT_DIR.glob('*.docx'))
    if not candidates:
        return None
    for candidate in candidates:
        if 'program_kılavuzu' in candidate.name.lower() or 'program_kilavuzu' in candidate.name.lower():
            return candidate
    return candidates[0]

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


def tbl_to_markdown(tbl_elem):
    """Word tbl öğesini Markdown tablo dizgesine çevirir."""
    rows = []
    for tr in tbl_elem.findall(f'{WNS}tr'):
        cells = []
        for tc in tr.findall(f'{WNS}tc'):
            # Her hücrenin içeriğini (metin + matematik) al
            cell_text = cell_tc_to_rich_text(tc).replace('\n', '<br>')
            cells.append(cell_text)
        if cells:
            rows.append(f"| {' | '.join(cells)} |")
    
    if not rows:
        return ""
    
    # Header separator
    col_count = len(rows[0].split('|')) - 2
    header_sep = f"| {' | '.join(['---'] * col_count)} |"
    if len(rows) > 1:
        rows.insert(1, header_sep)
    else:
        rows.append(header_sep)
        
    return '\n'.join(rows)


def cell_tc_to_rich_text(tc):
    """
    Bir tablo hücresinin (tc XML elemanı) içeriğini zengin metin olarak döner.
    - Normal metin: olduğu gibi
    - m:oMath inline: $...$
    - m:oMathPara display: $$...$$
    - w:tbl: Markdown şeklinde
    """
    parts = []
    # Hücre içindeki tüm çocukları sırasıyla gezmek için p ve tbl etiketlerine bakarız
    for child in tc:
        ctag = child.tag.split('}')[-1]
        
        if ctag == 'p':
            para_parts = []
            for item in child:
                itag = item.tag.split('}')[-1]
                if itag == 'r':
                    t = item.find(f'{WNS}t')
                    if t is not None and t.text:
                        para_parts.append(t.text)
                elif itag == 'hyperlink':
                    # Extract text from runs inside the hyperlink
                    for hr in item.findall(f'{WNS}r'):
                        ht = hr.find(f'{WNS}t')
                        if ht is not None and ht.text:
                            para_parts.append(ht.text)
                elif itag == 'oMath':
                    latex = omml_to_latex(item).strip()
                    if latex:
                        para_parts.append(f'${latex}$')
                elif itag == 'oMathPara':
                    for om in item.findall(f'{M}oMath'):
                        latex = omml_to_latex(om).strip()
                        if latex:
                            para_parts.append(f'$${latex}$$')
            line = ''.join(para_parts).strip()
            if line:
                parts.append(line)
        
        elif ctag == 'tbl':
            md_table = tbl_to_markdown(child)
            if md_table:
                parts.append('\n' + md_table + '\n')
                
    return '\n'.join(parts).strip()


# ─── Resim çıkarıcı ───────────────────────────────────────────────────────

def extract_images(tc, doc_part, course_code, img_base):
    """
    Hücreden tüm gömülü görselleri çıkarıp diske yazar.
    Döndürür: proje köküne göre göreli yol listesi.
    """
    saved = []
    # Standart DrawingML (inline & anchor)
    drawings = tc.findall(f'.//{DRAW}inline') + tc.findall(f'.//{DRAW}anchor')
    
    # Legacy VML (pict) ve Objects
    pict_elements = tc.findall(f'.//{{{WNS}}}pict')
    object_elements = tc.findall(f'.//{{{WNS}}}object')

    for elem in drawings + pict_elements + object_elements:
        try:
            # DrawingML blip search
            blip = elem.find(f'.//{{{A_NS}}}blip')
            r_embed = None
            if blip is not None:
                r_embed = blip.get(f'{{{EMB}}}embed')
            
            # Legacy/VML search (imagedata, shape/imagedata vb)
            if not r_embed:
                imagedata = elem.find(f'.//{{{WNS}}}imagedata')
                if imagedata is not None:
                    r_embed = imagedata.get(f'{{{EMB}}}id')
            
            if not r_embed:
                continue

            img_part  = doc_part.rels[r_embed].target_part
            img_bytes = img_part.blob
            ext       = img_part.partname.split('.')[-1].lower()
            
            out_dir   = os.path.join(img_base, course_code)
            os.makedirs(out_dir, exist_ok=True)
            
            fname = f'soru_{len(saved)+1}.{ext}'
            fpath = os.path.join(out_dir, fname)
            
            with open(fpath, 'wb') as f:
                f.write(img_bytes)
            
            # Proje köküne göre göreli yolu sakla (Users/gokcen/DPK temizlenerek)
            rel_path = os.path.relpath(fpath, ROOT_DIR)
            saved.append(rel_path)
            
        except Exception as e:
            # saved.append(f'[hata: {e}]')
            continue # Hataları sessizce geç veya logla
            
    return saved


# ─── Tablo ayrıştırıcılar ─────────────────────────────────────────────────

def text_of(elem):
    return ''.join(t.text or '' for t in elem.iter(f'{WNS}t')).strip()


def is_yellow_cell(cell):
    tcpr = cell._tc.find(f'{WNS}tcPr')
    if tcpr is not None:
        shd = tcpr.find(f'{WNS}shd')
        if shd is not None:
            fill = shd.get(f'{WNS}fill', '').upper()
            # Lenient yellow detection: common codes and anything starting with FFF (mostly yellow/orange/light)
            # FFFFFF is white, should be excluded.
            return (fill.startswith('FFF') and fill != 'FFFFFF') or fill == 'YELLOW'
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


def _add_kk_value(value, value_cell, result, current_topic, table_has_yellow=True):
    """Bir konu/kazanım değerini sonuç listesine ekler; güncel topic'i döner."""
    is_yellow = is_yellow_cell(value_cell)
    
    # "Konu ve ilgili kazanım" metni başlı başına bir kazanım veya konu olamaz.
    if "konu ve" in value.lower() and "kazanım" in value.lower():
        return current_topic

    if table_has_yellow:
        # If the table uses yellow, ONLY yellow cells are topics.
        is_topic = is_yellow
    else:
        # Fallback to punctuation heuristic if no yellow is used in the table (e.g. D0000106)
        is_topic = not value.endswith(('.', ';', ':', '?', '!')) and len(value) < 120 and not value.lower().startswith(('py', 'p.y'))

    if is_topic:
        current_topic = {'konu': value, 'kazanimlar': []}
        result['konu_ve_kazanimlar'].append(current_topic)
    else:
        if current_topic is None:
            current_topic = {'konu': value, 'kazanimlar': []}
            result['konu_ve_kazanimlar'].append(current_topic)
        else:
            current_topic['kazanimlar'].append(value)
    return current_topic


def parse_info_table(tbl):
    """İlk tablo: öğretim üyesi bilgileri + amaç + konu/kazanımlar."""
    result = {
        'ogretim_uyesi': '', 'oda_numarasi': '', 'ofis_saati': '',
        'eposta': '', 'ders_zamani': '', 'derslik': '',
        'dersin_amaci': '', 'konu_ve_kazanimlar': []
    }
    
    # Heuristic tier: Does this table use yellow shading at all?
    table_has_yellow = False
    for row in tbl.rows:
        ucells = _unique_cells(row)
        if len(ucells) >= 2:
            if is_yellow_cell(ucells[1]) or (len(ucells) > 2 and is_yellow_cell(ucells[-1])):
                table_has_yellow = True
                break

    current_topic = None
    in_kk_section = False
    for row in tbl.rows:
        ucells = _unique_cells(row)
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
        elif any(lbl.lower() in key.lower() for lbl in _KK_LABELS):
            in_kk_section = True
            actual_value = value
            actual_cell = value_cell
            if not actual_value and len(ucells) > 2:
                for cand in ucells[1:]:
                    cv = cand.text.strip()
                    if cv:
                        actual_value = cv
                        actual_cell = cand
                        break
            
            if actual_value:
                current_topic = _add_kk_value(actual_value, actual_cell, result, current_topic, table_has_yellow)
        elif key == '' and in_kk_section:
            cont_cell  = ucells[-1]
            cont_value = cont_cell.text.strip()
            if not cont_value:
                continue
            current_topic = _add_kk_value(cont_value, cont_cell, result, current_topic, table_has_yellow)
        elif key:
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
    default_docx = find_default_docx()
    parser = argparse.ArgumentParser(description='DOCX\'ten ders planlarini cikarir')
    parser.add_argument('--docx', default=str(default_docx) if default_docx else None, help='Kaynak DOCX yolu')
    parser.add_argument('--out', default=str(DEFAULT_JSON_OUT), help='Cikti JSON yolu')
    parser.add_argument('--img-base', default=str(DEFAULT_IMG_BASE), help='Gorsellerin yazilacagi klasor')
    args = parser.parse_args()

    if not args.docx:
        raise FileNotFoundError('Kaynak DOCX bulunamadi. --docx ile dosya yolu verin.')

    docx_path = Path(args.docx)
    json_out = Path(args.out)
    img_base = Path(args.img_base)

    doc      = docx.Document(str(docx_path))
    body     = doc.element.body
    children = list(body)
    tables   = doc.tables

    elem_to_tbl = {}
    ti = 0
    for i, c in enumerate(children):
        if c.tag.split('}')[-1] == 'tbl':
            elem_to_tbl[i] = ti
            ti += 1

    os.makedirs(img_base, exist_ok=True)
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
                    entry.update(parse_weekly_table(tbls[1], code, doc.part, str(img_base)))
                elif len(tbls) == 1:
                    w = parse_weekly_table(tbls[0], code, doc.part, str(img_base))
                    if w['haftalik_plan'] or w['degerlendirme']:
                        entry.update(w)

                courses[code] = entry

        i += 1

    json_out.parent.mkdir(parents=True, exist_ok=True)
    with open(json_out, 'w', encoding='utf-8') as f:
        json.dump(courses, f, ensure_ascii=False, indent=2)

    print(f"Toplam ders: {len(courses)}")
    print(f"JSON: {json_out}")
    img_count = sum(
        len(os.listdir(os.path.join(img_base, d)))
        for d in os.listdir(img_base)
        if os.path.isdir(os.path.join(img_base, d))
    )
    print(f"Kaydedilen görsel: {img_count} dosya ({img_base})")
    math_courses = [code for code, c in courses.items() if '$' in c.get('ornek_sorular', '')]
    img_courses  = [code for code, c in courses.items() if c.get('ornek_sorular_gorseller')]
    print(f"LaTeX math içeren: {math_courses}")
    print(f"Görsel içeren    : {img_courses}")


if __name__ == '__main__':
    main()
