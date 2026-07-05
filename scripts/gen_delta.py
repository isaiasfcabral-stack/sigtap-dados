#!/usr/bin/env python3
# Gera delta entre duas competencias do SIGTAP (formato JSON do app).
# Uso: python3 gen_diff.py <antiga.json> <nova.json> <saida.json>
import json, sys

def val(p):
    try: return float(p.get('totalHosp') or 0)
    except: return 0.0

ant_path, nov_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
ant = {p['codigo']: p for p in json.load(open(ant_path, encoding='utf-8'))}
nov = {p['codigo']: p for p in json.load(open(nov_path, encoding='utf-8'))}

comp_ant = next(iter(ant.values())).get('dtCompetencia','?')
comp_nov = next(iter(nov.values())).get('dtCompetencia','?')

incluidos = [{'codigo':c,'nome':nov[c]['nome']} for c in nov if c not in ant]
excluidos = [{'codigo':c,'nome':ant[c]['nome']} for c in ant if c not in nov]
reajustados = []
for c in nov:
    if c in ant:
        a, b = val(ant[c]), val(nov[c])
        if abs(a-b) > 0.001:
            var = (b-a)/a if a else None
            reajustados.append({'codigo':c,'nome':nov[c]['nome'],
                'antes':round(a,2),'agora':round(b,2),
                'variacao': round(var,4) if var is not None else None})
reajustados.sort(key=lambda x: abs(x['variacao'] or 0), reverse=True)

delta = {'de':comp_ant,'para':comp_nov,
    'resumo':{'incluidos':len(incluidos),'excluidos':len(excluidos),'reajustados':len(reajustados)},
    'incluidos':incluidos,'excluidos':excluidos,'reajustados':reajustados}
json.dump(delta, open(out_path,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
print(f"Competencias: {comp_ant} -> {comp_nov}")
print(f"Incluidos: {len(incluidos)} | Excluidos: {len(excluidos)} | Reajustados: {len(reajustados)}")
print("Top 3 reajustes:")
for r in reajustados[:3]:
    print(f"  {r['codigo']} {r['nome'][:40]}: R${r['antes']} -> R${r['agora']} ({(r['variacao'] or 0)*100:+.0f}%)")
