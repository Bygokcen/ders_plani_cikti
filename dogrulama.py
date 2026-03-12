import json

with open('/Users/gokcen/DPK/ders_planlari.json', encoding='utf-8') as f:
    data = json.load(f)

print("=== BM1007 - Lineer Cebir (OMML math) ===")
c = data['BM1007']
print(c['ornek_sorular'])

print("\n=== BM2010 - Nümerik Analiz (OMML math) ===")
c = data['BM2010']
print(c['ornek_sorular'][:500])

print("\n=== BM2011 - Diferansiyel Denklemler (OMML math) ===")
c = data['BM2011']
print(c['ornek_sorular'][:500])

print("\n=== BM1002 - Temel Elektrik (resimler) ===")
c = data['BM1002']
print("Metin:", c['ornek_sorular'][:200])
print("Görseller:", c['ornek_sorular_gorseller'])

print("\n=== BMS3007 - ML/DL (hem resim, hem? ) ===")
c = data.get('BMS3007', {})
print("Metin:", c.get('ornek_sorular','')[:200])
print("Görseller:", c.get('ornek_sorular_gorseller', []))
