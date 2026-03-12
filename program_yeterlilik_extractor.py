#!/usr/bin/env python3
"""
DOCX dosyasındaki "Dersler ve Program Yeterlilik İlişkisi" tablolarından
(ders planı tabloları) ders kodu -> program yeterlilikleri eşleşmesini çıkarır.

Girdi : /Users/gokcen/Downloads/Program_Kılavuzu_BILMUH2025-26_19022026.docx
Çıktı : /Users/gokcen/DPK/ders_planlari_cikti/ders_program_yeterlilikleri.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import docx

DOCX_PATH = Path("/Users/gokcen/Downloads/Program_Kılavuzu_BILMUH2025-26_19022026.docx")
JSON_OUT = Path("/Users/gokcen/DPK/ders_planlari_cikti/ders_program_yeterlilikleri.json")


def _clean(text: str) -> str:
    return " ".join((text or "").replace("\n", " ").split())


def _is_course_code(value: str) -> bool:
    value = _clean(value)
    if not value or " " in value:
        return False
    if value.startswith("Seçmeli"):
        return False
    # BM1001, D0000106, AİİT101, TD101 vb. kodları yakalar.
    return bool(re.search(r"\d", value)) and bool(re.fullmatch(r"[0-9A-Za-zÇĞİÖŞÜçğıöşü]+", value))


def _normalize_py_headers(headers: list[str]) -> list[tuple[int, str]]:
    """P başlıklarını kolon index'i ile birlikte döndürür.

    Bazı tablolarda birleştirme nedeniyle başlık tekrar edebiliyor (ör. P11, P11).
    Bu durumda ikinciyi sıralı şekilde P12 olarak adlandırır.
    """
    py_cols: list[tuple[int, str]] = []
    used_labels: set[str] = set()
    max_num = 0

    for idx, h in enumerate(headers):
        m = re.fullmatch(r"P\s*(\d+)", h, flags=re.IGNORECASE)
        if not m:
            continue

        base_num = int(m.group(1))
        max_num = max(max_num, base_num)
        label = f"P{base_num}"

        if label in used_labels:
            max_num += 1
            label = f"P{max_num}"

        used_labels.add(label)
        py_cols.append((idx, label))

    return py_cols


def _table_is_program_relation_table(tbl) -> bool:
    if len(tbl.rows) < 2:
        return False

    row0 = [_clean(c.text) for c in tbl.rows[0].cells]
    row1 = [_clean(c.text) for c in tbl.rows[1].cells]
    joined0 = " ".join(row0)

    has_plan_title = "Ders Planı" in joined0
    has_ders_kodu = any(x == "Ders Kodu" for x in row1)
    has_py = any(re.fullmatch(r"P\s*\d+", x, flags=re.IGNORECASE) for x in row1)

    return has_plan_title and has_ders_kodu and has_py


def extract_relations(docx_path: Path) -> dict:
    doc = docx.Document(str(docx_path))

    ders_to_pys: dict[str, list[str]] = {}
    ders_to_scores: dict[str, dict[str, str]] = {}
    used_tables: list[int] = []

    for ti, tbl in enumerate(doc.tables):
        if not _table_is_program_relation_table(tbl):
            continue

        used_tables.append(ti)

        header = [_clean(c.text) for c in tbl.rows[1].cells]
        py_cols = _normalize_py_headers(header)

        if not py_cols:
            continue

        for row in tbl.rows[2:]:
            cells = [_clean(c.text) for c in row.cells]
            if len(cells) < 2:
                continue

            ders_kodu = cells[0]
            if not _is_course_code(ders_kodu):
                continue

            py_list = ders_to_pys.setdefault(ders_kodu, [])
            py_scores = ders_to_scores.setdefault(ders_kodu, {})

            for col_idx, py_label in py_cols:
                if col_idx >= len(cells):
                    continue

                val = cells[col_idx]
                if not val or val == "-":
                    continue

                if py_label not in py_list:
                    py_list.append(py_label)
                py_scores[py_label] = val

    for code in ders_to_pys:
        ders_to_pys[code] = sorted(ders_to_pys[code], key=lambda x: int(x[1:]))

    return {
        "kaynak_docx": str(docx_path),
        "olusturulma_tarihi": datetime.now().isoformat(timespec="seconds"),
        "kullanilan_tablo_indexleri": used_tables,
        "ders_sayisi": len(ders_to_pys),
        "ders_program_yeterlilikleri": dict(sorted(ders_to_pys.items())),
        "ders_program_yeterlilik_puanlari": dict(sorted(ders_to_scores.items())),
    }


def main() -> None:
    if not DOCX_PATH.exists():
        raise FileNotFoundError(f"DOCX bulunamadı: {DOCX_PATH}")

    data = extract_relations(DOCX_PATH)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)

    with JSON_OUT.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"JSON yazıldı: {JSON_OUT}")
    print(f"Ders sayısı: {data['ders_sayisi']}")
    print(f"Kullanılan tablo indexleri: {data['kullanilan_tablo_indexleri']}")


if __name__ == "__main__":
    main()
