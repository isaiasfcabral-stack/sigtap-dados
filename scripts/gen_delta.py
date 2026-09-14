#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o delta entre duas competências do SIGTAP (formato JSON do app).

Uso: python3 gen_delta.py <antiga.json> <nova.json> <saida.json>

Além de inclusões, exclusões e reajuste de valor, registra MUDANÇAS DE REGRA
(idade, habilitação, descrição, quantidade máxima, CID…). Sem isso a 09/2026
saía como 0/0/0 mesmo tendo liberado etanercepte 25 mg até 130 anos (era 18),
mepolizumabe a partir de 12 (era 18) e tacrolimo pomada com 3 execuções (era 2).
"""
import json, sys

# Campos de VALOR: já viram "reajustados"; não podem virar "alterados" também.
CAMPOS_VALOR = {"vlSH", "vlSA", "vlSP", "totalHosp"}
# Ruído: muda em todo procedimento, ou é derivado de outro campo.
CAMPOS_IGNORADOS = {"codigo", "dtCompetencia", "cidSearch"}

# Campos que são listas coladas com " / ": mostrar o texto inteiro dá entradas de
# 6 KB (um CBO tem 200+ profissões). Resume-se em contagem + o que entrou/saiu.
CAMPOS_LISTA = {"cbo", "compativel", "incompativel", "obrigatoria",
                "habilitacao", "leito", "serClass"}
SEP = " / "
LIMITE_CURTO = 60     # até aqui mostra o valor literal
LIMITE_TEXTO = 240    # corte de texto livre (descrição, nome)
MAX_ITENS_DET = 5     # itens citados no detalhe

ROTULOS = {
    "nome": "Nome", "descricao": "Descrição", "complexidade": "Complexidade",
    "sexo": "Sexo", "idadeMin": "Idade mínima", "idadeMax": "Idade máxima",
    "financiamento": "Financiamento", "rubrica": "Rubrica", "registro": "Registro",
    "modalidade": "Modalidade", "qtMaxExecucao": "Qtd. máxima de execução",
    "qtDiasPermanencia": "Dias de permanência", "grupo": "Grupo",
    "subgrupo": "Subgrupo", "formaOrg": "Forma de organização", "cbo": "CBO",
    "habilitacao": "Habilitação", "leito": "Leito",
    "serClass": "Serviço/classificação", "cid": "CID",
    "compativel": "Compatíveis", "incompativel": "Incompatíveis",
    "obrigatoria": "Obrigatórias",
}


def val(p):
    try:
        return float(p.get("totalHosp") or 0)
    except (TypeError, ValueError):
        return 0.0


def _cids(p):
    c = p.get("cid")
    if isinstance(c, list):
        return sorted(x.get("code", "") for x in c if isinstance(x, dict))
    return []


def _cortar(v, limite=LIMITE_TEXTO):
    s = "" if v is None else str(v)
    return s if len(s) <= limite else s[:limite - 1] + "…"


def _itens(v):
    return [x.strip() for x in str(v or "").split(SEP) if x.strip()]


def _lado(v, n):
    """Valor curto sai literal; lista longa vira 'N itens'."""
    s = "" if v is None else str(v)
    if len(s) <= LIMITE_CURTO:
        return s
    return "%d itens" % n if n else "—"


def _entrou_saiu(a, b):
    entrou = [x for x in b if x not in a]
    saiu = [x for x in a if x not in b]
    partes = []
    for sinal, lst in (("+", entrou), ("−", saiu)):
        if lst:
            partes.append(sinal + ", ".join(_cortar(x, 40) for x in lst[:MAX_ITENS_DET])
                          + ("…" if len(lst) > MAX_ITENS_DET else ""))
    return "; ".join(partes)


def _resumir_lista(va, vb):
    a, b = _itens(va), _itens(vb)
    return _lado(va, len(a)), _lado(vb, len(b)), _entrou_saiu(a, b)


def _resumir_cid(antes, agora):
    return _entrou_saiu(antes, agora)


def mudancas_de_regra(a, b):
    """Diferenças de regra entre o mesmo procedimento em duas competências."""
    out = []
    for k in sorted(set(a) | set(b)):
        if k in CAMPOS_VALOR or k in CAMPOS_IGNORADOS:
            continue
        if k == "cid":
            ca, cb = _cids(a), _cids(b)
            if ca != cb:
                out.append({"campo": "cid", "rotulo": ROTULOS["cid"],
                            "antes": "%d CID" % len(ca), "agora": "%d CID" % len(cb),
                            "detalhe": _resumir_cid(ca, cb)})
            continue
        va, vb = a.get(k), b.get(k)
        if va == vb:
            continue
        if k in CAMPOS_LISTA:
            antes, agora, det = _resumir_lista(va, vb)
            m = {"campo": k, "rotulo": ROTULOS.get(k, k), "antes": antes, "agora": agora}
            if det:
                m["detalhe"] = _cortar(det, 300)
            out.append(m)
        elif isinstance(va, str) or isinstance(vb, str):
            out.append({"campo": k, "rotulo": ROTULOS.get(k, k),
                        "antes": _cortar(va), "agora": _cortar(vb)})
        else:
            out.append({"campo": k, "rotulo": ROTULOS.get(k, k), "antes": va, "agora": vb})
    return out


def calcular(ant_lista, nov_lista):
    ant = {p["codigo"]: p for p in ant_lista}
    nov = {p["codigo"]: p for p in nov_lista}

    comp_ant = next((p.get("dtCompetencia") for p in ant.values()), "?")
    comp_nov = next((p.get("dtCompetencia") for p in nov.values()), "?")

    incluidos = [{"codigo": c, "nome": nov[c]["nome"]} for c in nov if c not in ant]
    excluidos = [{"codigo": c, "nome": ant[c]["nome"]} for c in ant if c not in nov]

    reajustados, alterados = [], []
    for c in nov:
        if c not in ant:
            continue
        a, b = val(ant[c]), val(nov[c])
        if abs(a - b) > 0.001:
            var = (b - a) / a if a else None
            reajustados.append({"codigo": c, "nome": nov[c]["nome"],
                                "antes": round(a, 2), "agora": round(b, 2),
                                "variacao": round(var, 4) if var is not None else None})
        ms = mudancas_de_regra(ant[c], nov[c])
        if ms:
            alterados.append({"codigo": c, "nome": nov[c]["nome"], "mudancas": ms})

    reajustados.sort(key=lambda x: abs(x["variacao"] or 0), reverse=True)
    alterados.sort(key=lambda x: (-len(x["mudancas"]), x["codigo"]))

    return {"de": comp_ant, "para": comp_nov,
            "resumo": {"incluidos": len(incluidos), "excluidos": len(excluidos),
                       "reajustados": len(reajustados), "alterados": len(alterados)},
            "incluidos": incluidos, "excluidos": excluidos,
            "reajustados": reajustados, "alterados": alterados}


def main():
    ant_path, nov_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    delta = calcular(json.load(open(ant_path, encoding="utf-8")),
                     json.load(open(nov_path, encoding="utf-8")))
    json.dump(delta, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = delta["resumo"]
    print("Competencias: %s -> %s" % (delta["de"], delta["para"]))
    print("Incluidos: %d | Excluidos: %d | Reajustados: %d | Alterados: %d"
          % (r["incluidos"], r["excluidos"], r["reajustados"], r["alterados"]))
    for x in delta["reajustados"][:3]:
        print("  R$ %s %s: %s -> %s (%+.0f%%)"
              % (x["codigo"], x["nome"][:36], x["antes"], x["agora"], (x["variacao"] or 0) * 100))
    for x in delta["alterados"][:5]:
        m = x["mudancas"][0]
        print("  ~ %s %s: %s %r -> %r%s"
              % (x["codigo"], x["nome"][:34], m["rotulo"], m["antes"], m["agora"],
                 " (+%d)" % (len(x["mudancas"]) - 1) if len(x["mudancas"]) > 1 else ""))


if __name__ == "__main__":
    main()
