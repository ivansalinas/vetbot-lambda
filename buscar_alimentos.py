import json

with open('catalogo_siigo_raw.json', 'r', encoding='utf-8') as f:
    prods = json.load(f)

palabras = ['ROYAL','PURINA','PROPLAN','PRO PLAN','HILLS','PEDIGREE',
            'DOG CHOW','EUKANUBA','ACANA','ORIJEN','TASTE','NUPEC',
            'CHUNKY','DOGOURMET','RICOCAN','CAMPESTRE']

alimentos = [p for p in prods 
             if float(p.get('available_quantity', 0) or 0) > 0
             and any(w in p.get('name','').upper() for w in palabras)]

alimentos.sort(key=lambda x: x.get('name',''))

print(f"Total alimentos con stock: {len(alimentos)}\n")
print(f"{'Código':<18} {'Stock':>6}  Nombre")
print("─"*70)
for p in alimentos[:20]:
    stock = float(p.get('available_quantity', 0) or 0)
    precio = 0
    try:
        precio = int(p.get('prices',[{}])[0].get('price_list',[{}])[0].get('value',0) or 0)
    except: pass
    print(f"{p.get('code',''):<18} {int(stock):>5}u  ${precio:>10,}  {p.get('name','')[:40]}")
