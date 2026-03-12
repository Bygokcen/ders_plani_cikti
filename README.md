# ders_plani_cikti

Ana proje DPK için yardımcı bir proje. Ders planı içeren `.docx` dosyalarını
okuyarak biçimlendirilmiş çıktı `.docx` dosyası üretir.

## Kurulum

```bash
pip install -r requirements.txt
```

## Kullanım

```bash
python main.py <girdi.docx> [<cikti.docx>]
```

**Örnek:**

```bash
python main.py ders_plani.docx cikti.docx
```

`cikti.docx` belirtilmezse çıktı dosyası `cikti.docx` adıyla kaydedilir.

## Örnek Dosya Oluşturma

Test amaçlı örnek bir `.docx` ders planı dosyası oluşturmak için:

```bash
python ornek_olustur.py
```

Bu komut `ornek_ders_plani.docx` adında bir dosya oluşturur.

## Desteklenen Ders Planı Formatı

Giriş `.docx` dosyası aşağıdaki alanları **tablo** ya da **etiketli paragraf**
biçiminde içermelidir:

| Alan | Açıklama |
|---|---|
| Ders Adı | Dersin adı |
| Sınıf / Şube | Sınıf ve şube bilgisi |
| Konu | İşlenecek konu |
| Kazanımlar | Hedef kazanımlar |
| Süre | Ders süresi |
| Yöntem ve Teknikler | Kullanılacak yöntem/teknikler |
| Materyaller | Gerekli materyaller |
| Değerlendirme | Değerlendirme yöntemi |

**Tablo formatı:** Her satırda birinci hücre etiket, ikinci hücre değer olmalıdır.

**Paragraf formatı:** Her satır `Etiket: Değer` biçiminde yazılmalıdır.

## Testler

```bash
python -m pytest tests/ -v
```

## Proje Yapısı

```
ders_plani_cikti/
├── main.py            # Ana giriş noktası
├── docx_okuyucu.py    # .docx dosyasını okuyup ayrıştırır
├── cikti_ureteci.py   # Biçimlendirilmiş .docx çıktısı üretir
├── ornek_olustur.py   # Örnek girdi .docx dosyası oluşturur
├── requirements.txt
└── tests/
    └── test_ders_plani.py
```
