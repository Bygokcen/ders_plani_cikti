# Ders Planları — Çıkarım Projesi

Program kılavuzu DOCX dosyalarındaki ders planlarını makine-okunabilir JSON formatına dönüştürür.

---

## Klasör İçeriği

```text
ders_planlari_cikti/
├── README.md                          ← bu dosya
├── ders_planlari_extractor.py         ← ders planı çıkarım scripti
├── program_yeterlilikleri_extractor.py← program yeterlilik açıklamaları çıkarım scripti
├── program_yeterlilik_extractor.py    ← ders-program yeterlilik matrisi çıkarım scripti
├── ogretim_elemanlari_extractor.py    ← öğretim elemanı + fotoğraf çıkarım scripti
├── dogrulama.py                       ← LaTeX ve görsel doğrulama scripti
├── ders_planlari.json                 ← 55 dersin tüm verisi (462 KB)
├── program_yeterlilikleri.json        ← sayfa 8 program yeterlilik açıklamaları
├── ders_program_yeterlilikleri.json   ← ders-program yeterlilik matrisi
├── ogretim_elemanlari.json            ← 19 öğretim elemanı + fotoğraf yolları
├── ders_gorselleri/                   ← örnek soruların görselleri (20 dosya)
│   ├── BM1002/
│   ├── BM1003/
│   ├── BM2002/
│   ├── BM2005/
│   ├── BM2006/
│   ├── BM2009/
│   ├── BM3009/
│   ├── BMS3003/
│   ├── BMS3007/
│   └── BMS3008/
└── ogretim_elemanlari_foto/           ← 19 öğretim elemanının fotoğrafları (jpeg/png)
```

---

## Kullanım

### Gereksinimler

```bash
pip install python-docx lxml
```

### Genel Kullanım

Scriptler artık varsayılan olarak proje kökündeki ilk uygun `.docx` dosyasını bulmaya çalışır.
Farklı programlar için en güvenlisi, DOCX ve çıktı yollarını açıkça vermektir.

> Not: Mevcut extractor'lar DOCX yapısı (başlıklar, tablolar, hücre biçimleri) üzerinden çalışır.
> PDF dosyaları doğrudan desteklenmez; PDF->DOCX dönüşümü çoğu zaman tablo yapısını bozduğu için
> eksik/boş çıktı üretir. Sağlıklı sonuç için orijinal program kılavuzu DOCX dosyasını kullanın.

```bash
python3 ders_planlari_extractor.py \
  --docx "/tam/yol/Program_Kilavuzu.docx" \
  --out "/tam/yol/ders_planlari.json" \
  --img-base "/tam/yol/ders_gorselleri"

python3 ogretim_elemanlari_extractor.py \
  --docx "/tam/yol/Program_Kilavuzu.docx" \
  --out "/tam/yol/ogretim_elemanlari.json" \
  --img-base "/tam/yol/ogretim_elemanlari_foto"

python3 program_yeterlilikleri_extractor.py --docx "/tam/yol/Program_Kilavuzu.docx"
python3 program_yeterlilik_extractor.py --docx "/tam/yol/Program_Kilavuzu.docx"
```

### BÖTE Örneği

```bash
python3 program_yeterlilikleri_extractor.py --docx "/tam/yol/BOTE_Program_Kilavuzu.docx" --out "program_yeterlilikleri_bote.json"
python3 program_yeterlilik_extractor.py --docx "/tam/yol/BOTE_Program_Kilavuzu.docx" --out "ders_program_yeterlilikleri_bote.json"
python3 ogretim_elemanlari_extractor.py --docx "/tam/yol/BOTE_Program_Kilavuzu.docx" --out "ogretim_elemanlari_bote.json" --img-base "ogretim_elemanlari_foto_bote"
python3 ders_planlari_extractor.py --docx "/tam/yol/BOTE_Program_Kilavuzu.docx" --out "ders_planlari_bote.json" --img-base "ders_gorselleri_bote"
```

### Çalıştırma

```bash
python3 ders_planlari_extractor.py
```

Script şunları üretir:

- `ders_planlari.json` — tüm 55 dersin güncel verisi
- `ders_gorselleri/<KOD>/soru_N.{png|jpeg|emf}` — gömülü görseller

### Öğretim elemanları + fotoğraflar

```bash
python3 ogretim_elemanlari_extractor.py
```

Belgedeki öğretim kadrosu tablosunu otomatik bulup her elemanın
ad-soyad, e-posta, iç hat ve çalışma alanlarını çeker;
aynı hücredeki gömülü fotoğrafı `ogretim_elemanlari_foto/` klasörüne kaydeder.
Gerekirse `--table-index` ile tablo index'i elle verilebilir.

### Program yeterlilikleri

```bash
python3 program_yeterlilikleri_extractor.py
```

Belgedeki program yeterlilikleri tablosundan `PY1 ... PYn` açıklamalarını çıkarır
ve `program_yeterlilikleri.json` dosyasını üretir.

### Ders-program yeterlilik matrisi

```bash
python3 program_yeterlilik_extractor.py
```

Her ders planı tablosundaki `P1/P2/...` kolonlarını okuyup
`ders_program_yeterlilikleri.json` dosyasını üretir.

### Doğrulama

```bash
python3 dogrulama.py
```

Seçili dersler için LaTeX dönüşüm ve görsel yolu çıktısı verir.

---

## Canlı Ortama Yükleme

Canlı site: <https://yzdd.gop.edu.tr/dpks/>

Yükleyici scriptleri artık `--live` parametresiyle canlı API'yi otomatik seçer.

Önerilen sıra:

```bash
cd ders_planlari_cikti

# 0) DOCX'ten JSON üretimi
python3 program_yeterlilikleri_extractor.py
python3 program_yeterlilik_extractor.py
python3 ogretim_elemanlari_extractor.py
python3 ders_planlari_extractor.py

cd ders_planlari_cikti/yukleyici

# 1) OBS dersleri
python3 obs_ders_yukle.py --live --email "admin@gop.edu.tr" --password "..."

# 2) Öğretim elemanları (foto yükleme API üzerinden)
python3 ogretim_elemanlari_yukle.py --live --photo-mode api --email "admin@gop.edu.tr" --password "..."

# 3) Akademisyen atamaları
python3 akademisyen_ata.py --live --email "admin@gop.edu.tr" --password "..."

# 4) Ders planı / izlence
python3 ders_plani_yukle.py --live --email "admin@gop.edu.tr" --password "..."

# 5) Program yeterlilikleri (PY açıklamaları)
python3 program_yeterlilikleri_yukle.py --live --email "admin@gop.edu.tr" --password "..."

# 6) Program yeterlilik matrisi
python3 program_yeterlilik_api_uygula.py --live --email "admin@gop.edu.tr" --password "..."
```

Notlar:

- İsterseniz `--base-url` ile manuel URL verebilirsiniz (site URL veya doğrudan API URL).
- Scriptlerin hepsi varsayılan olarak ilgili JSON dosyalarını `ders_planlari_cikti/` içinden okur.
- Farklı bölüm/programlar için yükleyicilerde `--bolum-keyword`, `--bolum-ad`, `--bolum-kod`, `--fakulte-ad`, `--fakulte-kod` argümanları kullanılabilir.
- `program_yeterlilikleri_yukle.py`, mevcut PY kayıtlarını kod bazında bulur; yoksa oluşturur, açıklama değişmişse günceller.
- SSL sorununda geçici olarak `--insecure` kullanılabilir.

---

## ogretim_elemanlari.json Yapısı

JSON anahtarı slugified ad-soyaddan türetilir. Her nesne:

```json
{
  "Dr_Remzi_YILDIRIM": {
    "ad_soyad": "Prof. Dr. Remzi YILDIRIM",
    "eposta": "remzi.yildirim@gop.edu.tr",
    "ic_hat": "2908",
    "calisma_alanlari": "Gömülü Sistemler, Bilgi Sistemleri, Bilgisayar Sistem Yapısı ve Donanımı",
    "foto": "ders_planlari_cikti/ogretim_elemanlari_foto/Dr_Remzi_YILDIRIM.jpeg"
  }
}
```

| Alan | Açıklama |
|---|---|
| `ad_soyad` | Unvan dahil tam ad |
| `eposta` | @gop.edu.tr kurumsal adresi |
| `ic_hat` | Telefon iç hattı |
| `calisma_alanlari` | Araştırma / uzmanlık alanları |
| `foto` | Proje köküne göreli fotoğraf yolu (jpeg/png) |

---

## JSON Yapısı

Her ders kodu bir nesneye karşılık gelir:

```json
{
  "BM1001": {
    "ders_adi": "Bilgisayar Mühendisliğine Giriş",
    "ogretim_uyesi": "Dr. Öğr. Üyesi Yasemin Çetin Kaya",
    "oda_numarasi": "345",
    "ofis_saati": "Çarşamba(12:15-13:15)",
    "eposta": "yasemin.kaya@gop.edu.tr",
    "ders_zamani": "Cuma(09:30-12:15)",
    "derslik": "Amfi 2-2C",
    "dersin_amaci": "...",
    "konu_ve_kazanimlar": [
      {
        "konu": "Bilgisayar Mühendisliği Temel Kavramlar",
        "kazanimlar": ["Bilgisayar mühendisliğini tanımlar.", "..."]
      }
    ],
    "haftalik_plan": [
      { "hafta": 1, "ders_konusu": "Oryantasyon Haftası", "program_yeterliligi": "" }
    ],
    "sinav_tarihleri": ["Ara Sınav", "Dönem Sonu Sınavı", "Bütünleme Sınavı"],
    "degerlendirme": "...",
    "ornek_sorular": "...",
    "ornek_sorular_gorseller": [],
    "kaynak_kitap": "...",
    "yardimci_kaynaklar": "..."
  }
}
```

### Alan Açıklamaları

| Alan | Açıklama |
|---|---|
| `ders_adi` | Dersin tam adı |
| `ogretim_uyesi` | Ad-soyad ve unvan |
| `oda_numarasi` | Öğretim üyesi oda no |
| `ofis_saati` | Görüşme saati |
| `eposta` | Öğretim üyesi e-postası |
| `ders_zamani` | Gün ve saat |
| `derslik` | Derslik adı |
| `dersin_amaci` | Dersin amacı |
| `konu_ve_kazanimlar` | Konular (sarı hücre) ve ilgili kazanımlar listesi |
| `haftalik_plan` | 14 haftalık plan, hafta no + ders konusu + program yeterliliği |
| `sinav_tarihleri` | Ara/dönem sonu/bütünleme sınav tarihleri |
| `degerlendirme` | Not kırılımı (vize %, final % vb.) |
| `ornek_sorular` | Düz metin + `$LaTeX$` formüller |
| `ornek_sorular_gorseller` | Görsel içeren derslerde dosya yolları listesi |
| `kaynak_kitap` | Ana kaynak |
| `yardimci_kaynaklar` | Ek kaynaklar ve okuma listesi |

---

## Teknik Notlar

### Konu / Kazanım Ayrımı

Word dosyasında **Konu ve İlgili Kazanımlar** sütunundaki hücreler
sarı arka plan (`fill=FFFF00`) ile işaretlenmişse **konu başlığı**,
beyaz ise önceki konunun **kazanımı** olarak yorumlanır.

### OMML → LaTeX Dönüşümü

Word'ün iç matematik formatı (OMML) özyinelemeli olarak LaTeX'e çevrilir.
Desteklenen yapılar:

| OMML etiketi | LaTeX çıktısı |
|---|---|
| `m:f` | `\frac{pay}{payda}` |
| `m:sSup` | `{taban}^{üs}` |
| `m:sSub` | `{taban}_{alt}` |
| `m:rad` | `\sqrt{...}` veya `\sqrt[n]{...}` |
| `m:nary` | `\int`, `\sum`, `\prod` vb. |
| `m:d` | `\left(...\right)` |
| `m:func` | `\sin`, `\cos`, `\lim` vb. |
| `m:acc` | `\hat`, `\bar`, `\tilde` vb. |
| `m:m` | `\begin{matrix}...\end{matrix}` |

### Gömülü Görseller

Örnek sorularda Word'e eklenmiş resimler otomatik olarak
`ders_gorselleri/<DERS_KODU>/soru_N.{uzantı}` yoluna kaydedilir
ve JSON'da `ornek_sorular_gorseller` alanına yol listesi olarak eklenir.

Görsel bulunan dersler: BM1002, BM1003, BM2002, BM2005, BM2006,
BM2009, BM3009, BMS3003, BMS3007, BMS3008 (toplam 20 dosya)

LaTeX formül bulunan dersler: BM1007, BM2010, BM2011, BM3007, BM4003
