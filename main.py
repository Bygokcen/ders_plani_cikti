"""
Ders Planı Çıktı Aracı – Ana Giriş Noktası

Kullanım:
    python main.py <girdi.docx> [<cikti.docx>]

Argümanlar:
    girdi.docx   Ders planı içeren kaynak .docx dosyası
    cikti.docx   Oluşturulacak çıktı .docx dosyası (varsayılan: cikti.docx)

Örnek:
    python main.py ornek_ders_plani.docx sonuc.docx
"""

import sys

from docx_okuyucu import docx_oku
from cikti_ureteci import cikti_olustur


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print(__doc__)
        sys.exit(1)

    girdi_yolu = argv[0]
    cikti_yolu = argv[1] if len(argv) > 1 else "cikti.docx"

    try:
        print(f"Okunuyor: {girdi_yolu}")
        veri = docx_oku(girdi_yolu)

        print("Çıkarılan alanlar:")
        for alan, deger in veri.items():
            ozet = deger.replace("\n", " ")
            if len(ozet) > 60:
                ozet = ozet[:57] + "..."
            print(f"  {alan:20s}: {ozet}")

        print(f"\nÇıktı oluşturuluyor: {cikti_yolu}")
        cikti_olustur(veri, cikti_yolu)
        print("Tamamlandı.")

    except FileNotFoundError:
        print(f"Hata: '{girdi_yolu}' dosyası bulunamadı.", file=sys.stderr)
        sys.exit(1)
    except ValueError as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
