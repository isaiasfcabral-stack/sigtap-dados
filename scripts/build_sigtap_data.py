#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Converte o pacote TabelaUnificada do DATASUS (zip) no JSON que o app SIGTAP usa.

Uso:
  python3 build_sigtap_data.py TabelaUnificada_202607_vXXXX.zip saida/sigtap_data_202607.json
  python3 build_sigtap_data.py <zip> <saida.json> --ref gabarito.json   # valida contra um JSON conhecido

Validado em 05/07/2026: reproduz a base 202606 100% idêntica ao sigtap_data_202606.json
a partir do zip oficial. Regras derivadas empiricamente dessa validação:
  - idade: DATASUS grava em meses; app usa anos (floor v/12); 9999 = sem limite -> ""
  - qtMaxExecucao / qtDiasPermanencia: 9999 -> ""
  - sexo: I -> Ambos, N -> Não se aplica
  - financiamento: usa a sigla entre parênteses quando houver (ex.: PAB, MAC)
  - compatibilidades (rl_procedimento_compativel, TP_COMPATIBILIDADE):
      tipos 1/3/4 -> "compativel" (nas duas direções)
      tipo 2      -> "incompativel" (nas duas direções)
      tipo 5      -> "obrigatoria" (só direção principal -> compatível)
  - grupo/subgrupo/formaOrg: rótulos amigáveis vêm de rotulos_categorias.json
    (ao lado deste script); código novo sem rótulo cai em capitalização simples.
"""
import json, os, sys, csv, io, zipfile, tempfile, hashlib
from collections import defaultdict

ENC = "latin-1"
AQUI = os.path.dirname(os.path.abspath(__file__))

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__); sys.exit(1)
    zip_path, out_path = args[0], args[1]
    ref_path = None
    if "--ref" in sys.argv:
        ref_path = sys.argv[sys.argv.index("--ref") + 1]

    src = tempfile.mkdtemp(prefix="sigtap_")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(src)

    def layout(name):
        cols = []
        with open(os.path.join(src, name + "_layout.txt"), encoding=ENC) as f:
            for row in csv.DictReader(f):
                cols.append((row["Coluna"], int(row["Inicio"]) - 1, int(row["Fim"])))
        return cols

    def tabela(name):
        cols = layout(name)
        out = []
        with open(os.path.join(src, name + ".txt"), encoding=ENC) as f:
            for ln in f:
                ln = ln.rstrip("\r\n")
                if ln.strip():
                    out.append({c: ln[a:b].strip() for c, a, b in cols})
        return out

    def num(s):
        s = s.strip()
        return int(s) if s else 0

    def n99(s):
        v = num(s)
        return "" if v == 9999 else v

    def idade(s):
        v = num(s)
        return "" if v == 9999 else v // 12

    proc  = {r["CO_PROCEDIMENTO"]: r for r in tabela("tb_procedimento")}
    descr = {r["CO_PROCEDIMENTO"]: r["DS_PROCEDIMENTO"] for r in tabela("tb_descricao")}
    fin   = {r["CO_FINANCIAMENTO"]: r["NO_FINANCIAMENTO"] for r in tabela("tb_financiamento")}
    rub   = {r["CO_RUBRICA"]: r["NO_RUBRICA"] for r in tabela("tb_rubrica")}
    grp   = {r["CO_GRUPO"]: r["NO_GRUPO"] for r in tabela("tb_grupo")}
    sgr   = {r["CO_GRUPO"] + r["CO_SUB_GRUPO"]: r["NO_SUB_GRUPO"] for r in tabela("tb_sub_grupo")}
    forg  = {r["CO_GRUPO"] + r["CO_SUB_GRUPO"] + r["CO_FORMA_ORGANIZACAO"]: r["NO_FORMA_ORGANIZACAO"] for r in tabela("tb_forma_organizacao")}
    cidnm = {r["CO_CID"]: r["NO_CID"] for r in tabela("tb_cid")}
    ocup  = {r["CO_OCUPACAO"]: r["NO_OCUPACAO"] for r in tabela("tb_ocupacao")}
    modnm = {r["CO_MODALIDADE"]: r["NO_MODALIDADE"] for r in tabela("tb_modalidade")}
    leinm = {r["CO_TIPO_LEITO"]: r["NO_TIPO_LEITO"] for r in tabela("tb_tipo_leito")}

    def rel(name, k, v):
        d = defaultdict(list)
        for r in tabela(name):
            d[r[k]].append(r[v])
        return d

    rl_cid = rel("rl_procedimento_cid", "CO_PROCEDIMENTO", "CO_CID")
    rl_cbo = rel("rl_procedimento_ocupacao", "CO_PROCEDIMENTO", "CO_OCUPACAO")
    rl_mod = rel("rl_procedimento_modalidade", "CO_PROCEDIMENTO", "CO_MODALIDADE")
    rl_reg = rel("rl_procedimento_registro", "CO_PROCEDIMENTO", "CO_REGISTRO")
    rl_lei = rel("rl_procedimento_leito", "CO_PROCEDIMENTO", "CO_TIPO_LEITO")
    rl_hab = rel("rl_procedimento_habilitacao", "CO_PROCEDIMENTO", "CO_HABILITACAO")
    rl_srv = defaultdict(list)
    for r in tabela("rl_procedimento_servico"):
        rl_srv[r["CO_PROCEDIMENTO"]].append((r["CO_SERVICO"], r["CO_CLASSIFICACAO"]))

    COMPAT = defaultdict(set); INCOMP = defaultdict(set); OBRIG = defaultdict(set)
    for r in tabela("rl_procedimento_compativel"):
        a, b, t = r["CO_PROCEDIMENTO_PRINCIPAL"], r["CO_PROCEDIMENTO_COMPATIVEL"], r["TP_COMPATIBILIDADE"]
        if t in ("1", "3", "4"):
            COMPAT[a].add(b); COMPAT[b].add(a)
        elif t == "2":
            INCOMP[a].add(b); INCOMP[b].add(a)
        elif t == "5":
            OBRIG[a].add(b)

    CPX = {"0": "", "1": "Atenção Básica", "2": "Média Complexidade", "3": "Alta Complexidade"}
    SEXO = {"A": "Ambos", "I": "Ambos", "M": "Masculino", "F": "Feminino", "N": "Não se aplica"}
    REG_ABREV = {"01": "BPA-C", "02": "BPA-I", "03": "AIH-P", "04": "AIH-E", "05": "AIH-S",
                 "06": "APAC-P", "07": "APAC-S", "08": "RAAS-AD", "09": "RAAS-PS", "10": "e-SUS"}

    rot_path = os.path.join(AQUI, "rotulos_categorias.json")
    rot = json.load(open(rot_path, encoding="utf-8")) if os.path.exists(rot_path) else {"grupo": {}, "subgrupo": {}, "formaOrg": {}}
    rot_novos = []

    def caplabel(s):
        s = s.strip().lower()
        return s[:1].upper() + s[1:] if s else ""

    def rotulo(campo, cod, bruto):
        r = rot.get(campo, {}).get(cod)
        if r is None:
            rot_novos.append((campo, cod, bruto))
            return caplabel(bruto)
        return r

    def fin_label(name):
        if "(" in name and ")" in name:
            return name[name.rindex("(") + 1:name.rindex(")")]
        return name

    def nomecomp(codes):
        return " / ".join(c + " - " + proc[c]["NO_PROCEDIMENTO"] for c in sorted(codes) if c in proc)

    def joinnames(codes, table):
        return " / ".join(table.get(c, c) for c in sorted(set(codes)))

    out = []
    for co in sorted(proc):
        p = proc[co]
        vlSH = num(p["VL_SH"]) / 100.0
        vlSA = num(p["VL_SA"]) / 100.0
        vlSP = num(p["VL_SP"]) / 100.0
        cids = sorted(set(rl_cid.get(co, [])))
        out.append({
            "codigo": co,
            "nome": p["NO_PROCEDIMENTO"],
            "descricao": descr.get(co, ""),
            "complexidade": CPX.get(p["TP_COMPLEXIDADE"], ""),
            "sexo": SEXO.get(p["TP_SEXO"], p["TP_SEXO"]),
            "idadeMin": idade(p["VL_IDADE_MINIMA"]),
            "idadeMax": idade(p["VL_IDADE_MAXIMA"]),
            "vlSH": round(vlSH, 2), "vlSA": round(vlSA, 2), "vlSP": round(vlSP, 2),
            "totalHosp": round(vlSH + vlSA + vlSP, 2),
            "financiamento": fin_label(fin.get(p["CO_FINANCIAMENTO"], "")),
            "rubrica": rub.get(p["CO_RUBRICA"], ""),
            "registro": " / ".join(REG_ABREV.get(c, c) for c in sorted(set(rl_reg.get(co, [])))),
            "modalidade": joinnames(rl_mod.get(co, []), modnm),
            "qtMaxExecucao": n99(p["QT_MAXIMA_EXECUCAO"]),
            "qtDiasPermanencia": n99(p["QT_DIAS_PERMANENCIA"]),
            "grupo": co[:2] + " - " + rotulo("grupo", co[:2], grp.get(co[:2], "")),
            "subgrupo": co[:4] + " - " + rotulo("subgrupo", co[:4], sgr.get(co[:4], "")),
            "formaOrg": co[:6] + " - " + rotulo("formaOrg", co[:6], forg.get(co[:6], "")),
            "cid": [{"code": c, "name": cidnm.get(c, "")} for c in cids],
            "cidSearch": " ".join(cids),
            "cbo": " / ".join(c + "-" + ocup.get(c, "") for c in sorted(set(rl_cbo.get(co, [])))),
            "habilitacao": " / ".join(sorted(set(rl_hab.get(co, [])))),
            "leito": joinnames(rl_lei.get(co, []), leinm),
            "serClass": " / ".join(s + " - " + c for s, c in sorted(set(rl_srv.get(co, [])))),
            "compativel": nomecomp(COMPAT.get(co, set())),
            "incompativel": nomecomp(INCOMP.get(co, set())),
            "obrigatoria": nomecomp(OBRIG.get(co, set())),
            "dtCompetencia": p["DT_COMPETENCIA"],
        })

    comp = out[0]["dtCompetencia"] if out else "?"
    if len(out) < 4000:
        print("ERRO: só %d procedimentos — pacote suspeito, nada gravado." % len(out)); sys.exit(2)

    if ref_path:
        ref = json.load(open(ref_path, encoding="utf-8"))
        refd = {p["codigo"]: p for p in ref}
        gend = {p["codigo"]: p for p in out}
        difs = 0
        for co2, rp in refd.items():
            gp = gend.get(co2)
            if gp is None or rp != gp:
                difs += 1
                if difs <= 5:
                    if gp is None:
                        print("faltando:", co2)
                    else:
                        for k in rp:
                            if rp.get(k) != gp.get(k):
                                print("dif %s.%s\n  ref: %r\n  gen: %r" % (co2, k, str(rp.get(k))[:150], str(gp.get(k))[:150]))
        print("validação contra %s: %s" % (os.path.basename(ref_path),
              "IDÊNTICO" if difs == 0 and len(refd) == len(gend) else "%d divergências" % difs))

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(out, ensure_ascii=False, separators=(",", ": ")).encode("utf-8")
    open(out_path, "wb").write(blob)
    sha = hashlib.sha256(blob).hexdigest()
    print("gerado: %s" % out_path)
    print("competência: %s | procedimentos: %d | bytes: %d" % (comp, len(out), len(blob)))
    print("sha256: %s" % sha)
    if rot_novos:
        print("ATENÇÃO: %d categorias novas sem rótulo amigável (usei capitalização simples):" % len(rot_novos))
        for campo, cod, bruto in rot_novos[:20]:
            print("  %s %s: %s" % (campo, cod, bruto))
        print("Se quiser rótulo melhor, adicione em rotulos_categorias.json e rode de novo.")

if __name__ == "__main__":
    main()
