#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica se saiu competência nova no DATASUS e atualiza este repositório.

Automático (GitHub Actions ou local):   python3 scripts/atualizar.py
Manual com zip baixado no navegador:    python3 scripts/atualizar.py --zip TabelaUnificada_202607_vX.zip

O que faz: descobre a competência mais nova em
http://sigtap.datasus.gov.br/tabela-unificada/app/download.jsp, baixa o zip,
gera dados/sigtap_data_AAAAMM.json, o delta contra a competência anterior e
atualiza o manifest.json que o app consulta. Sem dependências além do Python 3.
"""
import json, os, re, sys, subprocess, hashlib, urllib.request, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("BASE_URL", "https://isaiasfcabral-stack.github.io/sigtap-dados")
DOWNLOAD_PAGE = "http://sigtap.datasus.gov.br/tabela-unificada/app/download.jsp"
UA = {"User-Agent": "Mozilla/5.0 (sigtap-dados; atualizacao mensal de dados publicos)"}

class DatasusIndisponivel(Exception):
    pass

def http_get(url, tentativas=3, timeout=180):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            print("tentativa %d falhou: %s" % (i + 1, e))
            time.sleep(15 * (i + 1))
    raise DatasusIndisponivel(url)

def main():
    manifest = json.load(open(os.path.join(RAIZ, "manifest.json"), encoding="utf-8"))
    atual = manifest["competencia"]

    # bootstrap: se a base da competência atual ainda não está no repo (ex.: primeira
    # execução, porque o arquivo de 20 MB não sobe pelo navegador), gera ela agora.
    base_atual_path = os.path.join(RAIZ, "dados", "sigtap_data_%s.json" % atual)
    if not os.path.exists(base_atual_path) and "--zip" not in sys.argv:
        try:
            pagina = http_get(DOWNLOAD_PAGE, timeout=60).decode("latin-1", "replace")
        except DatasusIndisponivel:
            print("AVISO: DATASUS indisponível para o bootstrap; tento na próxima execução.")
            return
        links = re.findall(r'href="([^"]*TabelaUnificada_(\d{6})_v\d+\.zip)"', pagina)
        alvo = [h for h, c in links if c == atual]
        if alvo:
            href = alvo[0]
            url_zip = href if href.startswith("http") else ("http://sigtap.datasus.gov.br" + href if href.startswith("/") else "http://sigtap.datasus.gov.br/tabela-unificada/app/" + href)
            print("bootstrap: gerando base %s que falta no repo" % atual)
            try:
                blob = http_get(url_zip)
            except DatasusIndisponivel:
                print("AVISO: zip do DATASUS indisponível para o bootstrap; tento na próxima execução.")
                return
            zb = os.path.join(RAIZ, "TabelaUnificada_%s.zip" % atual)
            open(zb, "wb").write(blob)
            subprocess.check_call([sys.executable, os.path.join(RAIZ, "scripts", "build_sigtap_data.py"), zb, base_atual_path])
            os.remove(zb)
            b = open(base_atual_path, "rb").read()
            manifest["base"] = {"url": "%s/dados/sigtap_data_%s.json" % (BASE_URL, atual),
                                "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b), "itens": len(json.loads(b))}
            manifest["historico"] = sorted(re.findall(r"sigtap_data_(\d{6})\.json", " ".join(os.listdir(os.path.join(RAIZ, "dados")))))
            json.dump(manifest, open(os.path.join(RAIZ, "manifest.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
            print("bootstrap concluído: dados/sigtap_data_%s.json publicado" % atual)
        else:
            print("bootstrap: competência %s não está mais na página do DATASUS" % atual)

    zip_local = None
    if "--zip" in sys.argv:
        zip_local = sys.argv[sys.argv.index("--zip") + 1]
        m = re.search(r"TabelaUnificada_(\d{6})_v\d+\.zip", os.path.basename(zip_local))
        if not m:
            raise SystemExit("nome do zip fora do padrão TabelaUnificada_AAAAMM_vX.zip")
        nova = m.group(1)
    else:
        try:
            pagina = http_get(DOWNLOAD_PAGE, timeout=60).decode("latin-1", "replace")
        except DatasusIndisponivel:
            print("AVISO: portal do DATASUS indisponível agora; tento de novo na próxima execução.")
            return
        links = re.findall(r'href="([^"]*TabelaUnificada_(\d{6})_v\d+\.zip)"', pagina)
        if not links:
            print("AVISO: página do DATASUS veio sem os links (instabilidade conhecida); tento de novo na próxima execução.")
            return
        href, nova = max(links, key=lambda x: x[1])
        if nova <= atual:
            print("nada novo: DATASUS está em %s, repo está em %s" % (nova, atual))
            return
        if href.startswith("http"):
            url_zip = href
        elif href.startswith("/"):
            url_zip = "http://sigtap.datasus.gov.br" + href
        else:
            url_zip = "http://sigtap.datasus.gov.br/tabela-unificada/app/" + href
        print("competência nova: %s (repo está em %s)" % (nova, atual))
        print("baixando", url_zip)
        blob = http_get(url_zip)
        zip_local = os.path.join(RAIZ, "TabelaUnificada_%s.zip" % nova)
        open(zip_local, "wb").write(blob)

    if nova <= atual:
        print("zip informado (%s) não é mais novo que o repo (%s); nada a fazer" % (nova, atual))
        return

    saida = os.path.join(RAIZ, "dados", "sigtap_data_%s.json" % nova)
    subprocess.check_call([sys.executable, os.path.join(RAIZ, "scripts", "build_sigtap_data.py"), zip_local, saida])

    anterior = os.path.join(RAIZ, "dados", "sigtap_data_%s.json" % atual)
    delta_rel = None
    if os.path.exists(anterior):
        os.makedirs(os.path.join(RAIZ, "deltas"), exist_ok=True)
        delta_path = os.path.join(RAIZ, "deltas", "delta_%s_%s.json" % (atual, nova))
        subprocess.check_call([sys.executable, os.path.join(RAIZ, "scripts", "gen_delta.py"), anterior, saida, delta_path])
        delta_rel = "deltas/delta_%s_%s.json" % (atual, nova)

    blob = open(saida, "rb").read()
    dados = json.loads(blob)
    manifest.update({
        "competencia": nova,
        "publicadoEm": time.strftime("%Y-%m-%d"),
        "base": {
            "url": "%s/dados/sigtap_data_%s.json" % (BASE_URL, nova),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "itens": len(dados),
        },
        "delta": ({"url": "%s/%s" % (BASE_URL, delta_rel), "de": atual, "para": nova} if delta_rel else None),
        "historico": sorted(re.findall(r"sigtap_data_(\d{6})\.json", " ".join(os.listdir(os.path.join(RAIZ, "dados"))))),
    })
    json.dump(manifest, open(os.path.join(RAIZ, "manifest.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    if os.path.dirname(zip_local) == RAIZ:
        os.remove(zip_local)  # não versionar o zip
    print("manifest atualizado para %s (%d procedimentos)" % (nova, len(dados)))

if __name__ == "__main__":
    main()
