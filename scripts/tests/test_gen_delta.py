#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes do delta entre competências.

Motivo: o delta 202608->202609 saiu 0/0/0 porque só olhava código e valor
hospitalar. As mudanças reais de 09/2026 foram de REGRA — etanercepte 25 mg
passou de 18 para 130 anos, mepolizumabe de 18 para 12, tacrolimo pomada de 2
para 3 execuções, e 100 procedimentos mudaram de habilitação.
"""
import os, sys, unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import json  # noqa: E402
import gen_delta  # noqa: E402


def proc(codigo, nome="X", **kw):
    p = {"codigo": codigo, "nome": nome, "dtCompetencia": "202608", "totalHosp": "10.00",
         "idadeMin": "", "idadeMax": "", "habilitacao": "", "descricao": "",
         "qtMaxExecucao": ""}
    p.update(kw)
    return p


class TestMudancasDeRegra(unittest.TestCase):
    def delta(self, ant, nov):
        return gen_delta.calcular(ant, nov)

    def test_idade_maxima_vira_alteracao(self):
        d = self.delta([proc("1", "ETANERCEPTE", idadeMax=18)],
                       [proc("1", "ETANERCEPTE", idadeMax=130, dtCompetencia="202609")])
        self.assertEqual(d["resumo"]["alterados"], 1)
        alt = d["alterados"][0]
        self.assertEqual(alt["codigo"], "1")
        campos = {m["campo"]: m for m in alt["mudancas"]}
        self.assertIn("idadeMax", campos)
        self.assertEqual(campos["idadeMax"]["antes"], 18)
        self.assertEqual(campos["idadeMax"]["agora"], 130)

    def test_idade_minima_habilitacao_descricao_e_qtmax(self):
        ant = [proc("1", idadeMin=18), proc("2", habilitacao="A"),
               proc("3", descricao=""), proc("4", qtMaxExecucao=2)]
        nov = [proc("1", idadeMin=12, dtCompetencia="202609"),
               proc("2", habilitacao="B", dtCompetencia="202609"),
               proc("3", descricao="NOVO TEXTO", dtCompetencia="202609"),
               proc("4", qtMaxExecucao=3, dtCompetencia="202609")]
        d = self.delta(ant, nov)
        self.assertEqual(d["resumo"]["alterados"], 4)
        campos = {a["mudancas"][0]["campo"] for a in d["alterados"]}
        self.assertEqual(campos, {"idadeMin", "habilitacao", "descricao", "qtMaxExecucao"})

    def test_dtCompetencia_nunca_conta_como_mudanca(self):
        """Muda nos 5023 procedimentos; se contasse, a tela viraria ruído puro."""
        d = self.delta([proc("1")], [proc("1", dtCompetencia="202609")])
        self.assertEqual(d["resumo"]["alterados"], 0)
        self.assertEqual(d["alterados"], [])

    def test_procedimento_novo_nao_vira_alterado(self):
        d = self.delta([], [proc("9", dtCompetencia="202609")])
        self.assertEqual(d["resumo"]["incluidos"], 1)
        self.assertEqual(d["resumo"]["alterados"], 0)

    def test_um_procedimento_com_duas_mudancas_e_um_item_so(self):
        d = self.delta([proc("1", idadeMin=18, idadeMax=60)],
                       [proc("1", idadeMin=12, idadeMax=130, dtCompetencia="202609")])
        self.assertEqual(d["resumo"]["alterados"], 1)
        self.assertEqual(len(d["alterados"][0]["mudancas"]), 2)


class TestComportamentoAntigoPreservado(unittest.TestCase):
    def test_inclusao_exclusao_e_reajuste_continuam(self):
        ant = [proc("1"), proc("2"), proc("3", totalHosp="10.00")]
        nov = [proc("1", dtCompetencia="202609"),
               proc("3", totalHosp="20.00", dtCompetencia="202609"),
               proc("4", dtCompetencia="202609")]
        d = gen_delta.calcular(ant, nov)
        self.assertEqual(d["resumo"]["incluidos"], 1)
        self.assertEqual(d["resumo"]["excluidos"], 1)
        self.assertEqual(d["resumo"]["reajustados"], 1)
        self.assertEqual(d["de"], "202608")
        self.assertEqual(d["para"], "202609")
        r = d["reajustados"][0]
        self.assertEqual((r["antes"], r["agora"]), (10.0, 20.0))
        self.assertAlmostEqual(r["variacao"], 1.0)

    def test_reajuste_nao_aparece_duplicado_em_alterados(self):
        d = gen_delta.calcular([proc("1", totalHosp="10.00")],
                               [proc("1", totalHosp="20.00", dtCompetencia="202609")])
        self.assertEqual(d["resumo"]["reajustados"], 1)
        self.assertEqual(d["resumo"]["alterados"], 0)


class TestCamposLongos(unittest.TestCase):
    """CBO/compatíveis são listas gigantes: sem resumo, uma entrada dá 6 KB ilegíveis."""

    def test_lista_longa_vira_contagem_mais_resumo(self):
        longa = " / ".join("%06d-Profissional %d" % (i, i) for i in range(120))
        d = gen_delta.calcular([proc("1", cbo=longa)],
                               [proc("1", cbo="226320-Naturólogo", dtCompetencia="202609")])
        m = d["alterados"][0]["mudancas"][0]
        self.assertEqual(m["campo"], "cbo")
        self.assertEqual(m["antes"], "120 itens")
        self.assertEqual(m["agora"], "226320-Naturólogo")   # curto: mostra literal
        self.assertIn("−", m["detalhe"])
        self.assertLess(len(json.dumps(m, ensure_ascii=False)), 600)

    def test_habilitacao_curta_aparece_literal_com_o_que_entrou(self):
        d = gen_delta.calcular([proc("1", habilitacao="3805")],
                               [proc("1", habilitacao="3801 / 3805 / 3806",
                                     dtCompetencia="202609")])
        m = d["alterados"][0]["mudancas"][0]
        self.assertEqual(m["antes"], "3805")
        self.assertEqual(m["agora"], "3801 / 3805 / 3806")
        self.assertIn("3801", m["detalhe"])
        self.assertIn("3806", m["detalhe"])

    def test_descricao_gigante_e_truncada(self):
        d = gen_delta.calcular([proc("1", descricao="A" * 50)],
                               [proc("1", descricao="B" * 3000, dtCompetencia="202609")])
        m = d["alterados"][0]["mudancas"][0]
        self.assertLessEqual(len(m["agora"]), 250)
        self.assertTrue(m["agora"].endswith("…"))

    def test_custo_por_item_fica_pequeno(self):
        """O delta viaja no celular: nenhuma entrada pode voltar a pesar KBs."""
        longa = " / ".join("%06d-Profissional %d" % (i, i) for i in range(120))
        ant = [proc(str(i), cbo=longa, descricao="X" * 2000) for i in range(200)]
        nov = [proc(str(i), cbo="226320-Naturólogo", descricao="Y" * 2000,
                    dtCompetencia="202609") for i in range(200)]
        d = gen_delta.calcular(ant, nov)
        self.assertEqual(d["resumo"]["alterados"], 200)
        pior = max(len(json.dumps(a, ensure_ascii=False)) for a in d["alterados"])
        self.assertLess(pior, 900, "entrada de %d bytes" % pior)


if __name__ == "__main__":
    unittest.main(verbosity=2)
