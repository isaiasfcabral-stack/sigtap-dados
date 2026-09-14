#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da descoberta de competência do DATASUS.

Fixtures são respostas reais capturadas em 14/09/2026:
  competencias.rss            -> feed oficial, lista 09/2026 (publicada em 11/09/2026)
  download_indisponivel.html  -> download.jsp no estado "serviço indisponível"
                                 (sem nenhum link de zip), que é o estado em que o
                                 scraper antigo ficava calado e o workflow ficava verde.
"""
import os, sys, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import atualizar  # noqa: E402

FIX = os.path.join(AQUI, "fixtures")


def ler(nome, binario=True):
    with open(os.path.join(FIX, nome), "rb") as f:
        b = f.read()
    return b if binario else b.decode("utf-8")


class TestDescobertaPeloRSS(unittest.TestCase):
    """O feed RSS é a fonte estável; o download.jsp não é."""

    def test_acha_a_competencia_mais_nova(self):
        comp, url = atualizar.competencia_mais_nova(ler("competencias.rss"))
        self.assertEqual(comp, "202609")
        self.assertEqual(
            url,
            "ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/"
            "TabelaUnificada_202609_v2609111202.zip",
        )

    def test_nao_escolhe_por_ordem_do_feed_e_sim_pela_maior(self):
        # o feed vem em ordem decrescente hoje, mas isso não é contrato do DATASUS
        comp, _ = atualizar.competencia_mais_nova(ler("competencias.rss"))
        todas = atualizar.competencias_do_rss(ler("competencias.rss"))
        self.assertEqual(comp, max(todas))
        self.assertGreater(len(todas), 50)


class TestPaginaIndisponivel(unittest.TestCase):
    """Fonte sem links tem de ser ERRO, não 'nada novo'."""

    def test_pagina_sem_links_levanta(self):
        with self.assertRaises(atualizar.DatasusIndisponivel):
            atualizar.competencia_mais_nova(ler("download_indisponivel.html"))


class TestResolucaoDeURL(unittest.TestCase):
    """O bug literal do log de 13/09/2026: href ftp:// virou caminho do sigtap."""

    def test_ftp_absoluto_fica_intacto(self):
        href = ("ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/"
                "TabelaUnificada_202609_v2609111202.zip")
        self.assertEqual(atualizar.resolver_url(href), href)

    def test_http_absoluto_fica_intacto(self):
        href = "http://exemplo.gov.br/a.zip"
        self.assertEqual(atualizar.resolver_url(href), href)

    def test_caminho_absoluto_ganha_o_host(self):
        self.assertEqual(
            atualizar.resolver_url("/tabela-unificada/x.zip"),
            "http://sigtap.datasus.gov.br/tabela-unificada/x.zip",
        )

    def test_caminho_relativo_ganha_o_diretorio_do_app(self):
        self.assertEqual(
            atualizar.resolver_url("x.zip"),
            "http://sigtap.datasus.gov.br/tabela-unificada/app/x.zip",
        )


class TestManifestCoerente(unittest.TestCase):
    """Defeito nº3: o manifest anunciava um arquivo que não existia (HTTP 404)."""

    def test_manifest_apontando_para_arquivo_ausente_e_incoerente(self):
        manifest = {"competencia": "202606",
                    "base": {"url": "https://x/dados/sigtap_data_202606.json"}}
        self.assertFalse(atualizar.manifest_coerente(manifest, dados_presentes=[]))

    def test_manifest_com_o_arquivo_presente_e_coerente(self):
        manifest = {"competencia": "202609",
                    "base": {"url": "https://x/dados/sigtap_data_202609.json"}}
        self.assertTrue(
            atualizar.manifest_coerente(manifest, dados_presentes=["sigtap_data_202609.json"])
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
