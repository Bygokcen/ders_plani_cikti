#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import docx


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DOCX_PATH = ROOT_DIR / "Program_Kılavuzu_BILMUH2025-26_19022026 copy.docx"
DEFAULT_JSON_OUT = Path(__file__).resolve().with_name("program_yeterlilikleri.json")


def clean_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split())


def normalize_code(value: str) -> str | None:
    match = re.fullmatch(r"P\s*Y?\s*(\d+)", clean_text(value), flags=re.IGNORECASE)
    if not match:
        return None
    return f"PY{int(match.group(1))}"


def row_texts(row) -> list[str]:
    return [clean_text(cell.text) for cell in row.cells]


def extract_program_outcomes(docx_path: Path) -> dict:
    document = docx.Document(str(docx_path))

    table_indexes: list[int] = []
    outcome_map: dict[str, str] = {}

    for table_index, table in enumerate(document.tables):
        table_rows = [row_texts(row) for row in table.rows]
        table_outcomes: dict[str, str] = {}

        for cells in table_rows:
            if len(cells) < 2:
                continue

            code = normalize_code(cells[0])
            if not code:
                continue

            description_parts = [part for part in cells[1:] if part]
            description = clean_text(" ".join(description_parts)).lstrip("- ").strip()
            if not description:
                continue

            table_outcomes[code] = description

        if not table_outcomes:
            continue

        if len(table_outcomes) < 3:
            continue

        table_indexes.append(table_index)
        for code, description in table_outcomes.items():
            outcome_map.setdefault(code, description)

    ordered_codes = sorted(outcome_map, key=lambda item: int(re.search(r"\d+", item).group(0)))
    outcomes = [{"kod": code, "aciklama": outcome_map[code]} for code in ordered_codes]

    return {
        "kaynak_docx": str(docx_path),
        "olusturulma_tarihi": datetime.now().isoformat(timespec="seconds"),
        "kullanilan_tablo_indexleri": table_indexes,
        "program_yeterliligi_sayisi": len(outcomes),
        "program_yeterlilikleri": outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DOCX'ten program yeterliliklerini cikarir")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX_PATH), help="Kaynak DOCX yolu")
    parser.add_argument("--out", default=str(DEFAULT_JSON_OUT), help="Cikti JSON yolu")
    args = parser.parse_args()

    docx_path = Path(args.docx)
    out_path = Path(args.out)

    if not docx_path.exists():
        raise FileNotFoundError(f"DOCX bulunamadi: {docx_path}")

    data = extract_program_outcomes(docx_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)

    print(f"JSON yazildi: {out_path}")
    print(f"Program yeterliligi sayisi: {data['program_yeterliligi_sayisi']}")
    print(f"Kullanilan tablo indexleri: {data['kullanilan_tablo_indexleri']}")


if __name__ == "__main__":
    main()