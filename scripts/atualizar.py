#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verifica se saiu competência nova no DATASUS e atualiza este repositório.

Automático (GitHub Actions ou local):   python3 scripts/atualizar.py
Manual com zip baixado no navegador:    python3 scripts/atualizar.py --zip TabelaUnificada_202609_vX.zip

Fonte da verdade: o feed http://sigtap.datasus.gov.br/tabela-unificada/competencias.rss
(a própria download.jsp o anuncia). O feed é estável; a download.jsp passa longos
períodos exibindo "o serviço de downloads encontra-se indisponível", sem link nenhum —
foi o que manteve este repositório parado em 202606 de julho a setembro de 2026.
A download.jsp continua como fonte reserva.

Regras de saída (o workflow depende delas):
  - competência nova publicada ....... sai 0 e mexe nos arquivos
  - nada novo e manifest coerente .... sai 0 sem mexer em nada
  - não deu para verificar ........... sai != 0 (o workflow fica VERMELHO de propósito)
"""
import json, os, re, sys, subprocess, hashlib, urllib.request, gzip, time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("BASE_URL", "https://isaiasfcabral-stack.github.io/sigtap-dados")
RSS_URL = "http://sigtap.datasus.gov.br/tabela-unificada/competencias.rss"
DOWNLOAD_PAGE = "http://sigtap.datasus.gov.br/tabela-unificada/app/download.jsp"
HOST = "http://sigtap.datasus.gov.br"
DIR_APP = "http://sigtap.datasus.gov.br/tabela-unificada/app/"
UA = {"User-Agent": "Mozilla/5.0 (sigtap-dados; atualizacao mensal de dados publicos)"}

# casa tanto <link>ftp://...zip</link> (RSS) quanto href="...zip" (HTML)
RE_PACOTE = re.compile(r'([^\s"\'<>]*TabelaUnificada_(\d{6})_v\d+\.zip)')


class DatasusIndisponivel(Exception):
    pass


def _texto(blob):
    """Bytes -> str. O DATASUS devolve o RSS sempre gzipado e a JSP em latin-1."""
    if isinstance(blob, str):
        return blob
    if blob[:2] == b"\x1f\x8b":
        blob = gzip.decompress(blob)
    return blob.decode("utf-8", "replace")


def resolver_url(href):
    """Transforma o href do DATASUS numa URL buscável.

    Os links do portal são ftp://ftp2.datasus.gov.br/... . A versão antiga só
    tratava 'http' e '/', então o ftp:// caía no ramo relativo e virava
    http://sigtap.datasus.gov.br/tabela-unificada/app/ftp://... -> 404.
    """
    if re.match(r'^[a-zA-Z][a-zA-Z0-9+.\-]*://', href):
        return href
    if href.startswith("//"):
        return "http:" + href
    if href.startswith("/"):
        return HOST + href
    return DIR_APP + href


def competencias_do_rss(blob):
    """{'202609': 'ftp://...zip', ...} a partir do RSS ou do HTML da download.jsp."""
    achados = {}
    for url, comp in RE_PACOTE.findall(_texto(blob)):
        # o feed repete o link em <link> e <guid>; a primeira ocorrência basta
        achados.setdefault(comp, resolver_url(url))
    return achados


def competencia_mais_nova(blob):
    """(competencia, url) da maior competência anunciada.

    Levanta DatasusIndisponivel quando a fonte não traz pacote nenhum — é erro,
    não 'nada novo': tratar os dois casos igual foi o que deixou 10 execuções
    seguidas verdes sem publicar nada.
    """
    achados = competencias_do_rss(blob)
    if not achados:
        raise DatasusIndisponivel("fonte do DATASUS sem nenhum pacote TabelaUnificada")
    comp = max(achados)
    return comp, achados[comp]


def manifest_coerente(manifest, dados_presentes):
    """O arquivo que o manifest anuncia existe mesmo?

    O manifest apontava para dados/sigtap_data_202606.json, que nunca foi para o
    repositório: o app via 'competência nova' e baixava um HTTP 404.
    """
    url = (manifest.get("base") or {}).get("url") or ""
    if not url:
        return False
    return os.path.basename(url) in set(dados_presentes)


def dados_presentes():
    d = os.path.join(RAIZ, "dados")
    return [n for n in os.listdir(d) if n.endswith(".json")] if os.path.isdir(d) else []


def http_get(url, tentativas=3, timeout=180):
    erro = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            erro = e
            print("tentativa %d falhou (%s): %s" % (i + 1, url, e))
            if i + 1 < tentativas:
                time.sleep(15 * (i + 1))
    raise DatasusIndisponivel("%s: %s" % (url, erro))


def descobrir():
    """Tenta o RSS; se falhar, a download.jsp. Só desiste se as duas falharem."""
    erros = []
    for nome, url in (("RSS", RSS_URL), ("download.jsp", DOWNLOAD_PAGE)):
        try:
            comp, zip_url = competencia_mais_nova(http_get(url, timeout=60))
            print("fonte %s: competência mais nova = %s" % (nome, comp))
            return comp, zip_url
        except DatasusIndisponivel as e:
            print("fonte %s indisponível: %s" % (nome, e))
            erros.append("%s (%s)" % (nome, e))
    raise DatasusIndisponivel("nenhuma fonte respondeu: " + "; ".join(erros))


def gerar_base(zip_local, comp):
    saida = os.path.join(RAIZ, "dados", "sigtap_data_%s.json" % comp)
    subprocess.check_call([sys.executable,
                           os.path.join(RAIZ, "scripts", "build_sigtap_data.py"),
                           zip_local, saida])
    return saida


def baixar_zip(url, comp):
    blob = http_get(url)
    if blob[:2] != b"PK":
        raise DatasusIndisponivel("o que veio de %s não é um zip" % url)
    caminho = os.path.join(RAIZ, "TabelaUnificada_%s.zip" % comp)
    open(caminho, "wb").write(blob)
    return caminho


def escrever_manifest(manifest, comp, base_path, delta_rel, de=None):
    blob = open(base_path, "rb").read()
    manifest.update({
        "competencia": comp,
        "publicadoEm": time.strftime("%Y-%m-%d"),
        "base": {
            "url": "%s/dados/sigtap_data_%s.json" % (BASE_URL, comp),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bytes": len(blob),
            "itens": len(json.loads(blob)),
        },
        "delta": ({"url": "%s/%s" % (BASE_URL, delta_rel), "de": de, "para": comp}
                  if delta_rel else None),
        "historico": sorted(re.findall(r"sigtap_data_(\d{6})\.json", " ".join(dados_presentes()))),
    })
    json.dump(manifest, open(os.path.join(RAIZ, "manifest.json"), "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    if not manifest_coerente(manifest, dados_presentes()):
        raise SystemExit("ERRO: manifest ficou apontando para arquivo ausente")


def main():
    manifest = json.load(open(os.path.join(RAIZ, "manifest.json"), encoding="utf-8"))
    atual = manifest["competencia"]

    if "--zip" in sys.argv:
        zip_local = sys.argv[sys.argv.index("--zip") + 1]
        m = re.search(r"TabelaUnificada_(\d{6})_v\d+\.zip", os.path.basename(zip_local))
        if not m:
            raise SystemExit("nome do zip fora do padrão TabelaUnificada_AAAAMM_vX.zip")
        nova, zip_url = m.group(1), None
    else:
        nova, zip_url = descobrir()
        zip_local = None

    coerente = manifest_coerente(manifest, dados_presentes())
    if nova <= atual:
        if coerente:
            print("nada novo: DATASUS está em %s, repo está em %s" % (nova, atual))
            return
        # manifest anuncia arquivo que não existe: republica a competência atual
        print("manifest incoerente (dados/%s ausente): regerando %s" %
              (os.path.basename((manifest.get("base") or {}).get("url", "?")), atual))
        nova = atual
        if zip_local is None:
            achados = {}
            for url in (RSS_URL, DOWNLOAD_PAGE):
                try:
                    achados = competencias_do_rss(http_get(url, timeout=60))
                    if achados:
                        break
                except DatasusIndisponivel:
                    continue
            if atual not in achados:
                raise SystemExit(
                    "ERRO: competência %s não está mais no DATASUS e o arquivo dela não "
                    "está no repo. Publique uma competência disponível." % atual)
            zip_local = baixar_zip(achados[atual], atual)
    else:
        print("competência nova: %s (repo está em %s)" % (nova, atual))
        if zip_local is None:
            print("baixando", zip_url)
            zip_local = baixar_zip(zip_url, nova)

    saida = gerar_base(zip_local, nova)

    delta_rel, de = None, None
    anterior = os.path.join(RAIZ, "dados", "sigtap_data_%s.json" % atual)
    if nova != atual and os.path.exists(anterior):
        os.makedirs(os.path.join(RAIZ, "deltas"), exist_ok=True)
        delta_rel = "deltas/delta_%s_%s.json" % (atual, nova)
        subprocess.check_call([sys.executable,
                               os.path.join(RAIZ, "scripts", "gen_delta.py"),
                               anterior, saida, os.path.join(RAIZ, delta_rel)])
        de = atual

    escrever_manifest(manifest, nova, saida, delta_rel, de)

    if os.path.dirname(zip_local) == RAIZ:
        os.remove(zip_local)  # não versionar o zip
    print("manifest atualizado para %s" % nova)


if __name__ == "__main__":
    try:
        main()
    except DatasusIndisponivel as e:
        # falha RUIDOSA: antes isso saía 0 e o workflow ficava verde sem publicar nada
        print("ERRO: não deu para verificar o DATASUS: %s" % e)
        sys.exit(1)
