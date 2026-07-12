"""Testes da análise heurística de aderência (iauto.dominio.analise)."""

from iauto.dominio.analise import (
    NOTA_ADERENTE,
    NOTA_PARCIAL,
    PALAVRAS_MINIMAS,
    analisar_entrevista,
    avaliar_resposta,
    cobertura,
    recomendacao_por_nota,
    situacao_por_nota,
)
from iauto.dominio.modelos import Competencia, Resposta, Vaga
from iauto.dominio.roteiro import normalizar

# Resposta com cobertura total de termos, marcador de exemplo e mais de
# 80 palavras: atinge a pontuação máxima da heurística (60 + 25 + 15).
RESPOSTA_RICA = (
    "No projeto de vendas eu implementei consultas SQL com join e "
    "modelagem de tabela para o time comercial. "
    + "Depois disso acompanhei a evolucao dos numeros com o time toda semana. "
    * 6
)


def _resposta(competencia: str | None, texto: str, tipo: str = "competencia") -> Resposta:
    """Atalho para construir uma Resposta de teste."""
    return Resposta(
        id=1,
        tipo=tipo,
        competencia=competencia,
        pergunta=f"Fale sobre {competencia or 'você'}.",
        resposta=texto,
    )


class TestConstantes:
    """Os limiares compartilhados não devem mudar silenciosamente."""

    def test_valores_dos_limiares(self):
        assert NOTA_ADERENTE == 70
        assert NOTA_PARCIAL == 40
        assert PALAVRAS_MINIMAS == 15


class TestAvaliarResposta:
    def test_resposta_vazia_e_lacuna_sem_resposta(self):
        resultado = avaliar_resposta("", ["sql"])

        assert resultado["nota"] == 0
        assert resultado["situacao"] == "lacuna"
        assert resultado["riscos"] == ["pergunta ficou sem resposta"]
        assert resultado["n_palavras"] == 0
        assert resultado["termos_identificados"] == []
        assert resultado["tem_exemplo"] is False

    def test_resposta_so_com_espacos_conta_como_vazia(self):
        resultado = avaliar_resposta("   ", ["sql"])
        assert resultado["nota"] == 0
        assert resultado["riscos"] == ["pergunta ficou sem resposta"]

    def test_resposta_rica_e_aderente_com_nota_maxima(self):
        termos = ["sql", "join", "modelagem", "tabela"]
        resultado = avaliar_resposta(RESPOSTA_RICA, termos)

        assert resultado["n_palavras"] >= 80
        assert resultado["tem_exemplo"] is True
        assert resultado["nota"] == 100
        assert resultado["situacao"] == "aderente"
        assert resultado["riscos"] == []
        assert sorted(resultado["termos_identificados"]) == sorted(termos)

    def test_resposta_curta_gera_riscos_de_conteudo(self):
        resultado = avaliar_resposta("Sei usar sql", ["sql"])

        assert resultado["n_palavras"] < PALAVRAS_MINIMAS
        assert "resposta muito curta, com pouco conteúdo avaliável" in resultado["riscos"]
        assert "não apresentou exemplo concreto nem resultado" in resultado["riscos"]

    def test_trechos_relevantes_trazem_a_frase_que_cita_o_termo(self):
        resposta = "Comecei na área comercial. Depois migrei para consultas sql pesadas."
        resultado = avaliar_resposta(resposta, ["sql"])

        assert resultado["trechos_relevantes"] == ["Depois migrei para consultas sql pesadas."]


class TestCobertura:
    def test_encontra_termo_com_acentuacao_diferente(self):
        """Resposta sem acento cobre palavra-chave acentuada, e vice-versa."""
        resposta_norm = normalizar("Foquei em otimizacao e criação de índice.")
        proporcao, encontrados = cobertura(resposta_norm, ["otimização", "indice"])

        assert proporcao == 1.0
        # Devolve os termos na grafia original da vaga, não a normalizada.
        assert encontrados == ["otimização", "indice"]

    def test_sem_palavras_chave_a_proporcao_e_zero(self):
        assert cobertura("qualquer texto", []) == (0.0, [])

    def test_cobertura_parcial(self):
        proporcao, encontrados = cobertura("usei python no dia a dia", ["python", "pandas"])
        assert proporcao == 0.5
        assert encontrados == ["python"]


class TestSituacaoPorNota:
    def test_limiar_de_aderente(self):
        assert situacao_por_nota(70, "resposta qualquer") == "aderente"
        assert situacao_por_nota(69, "resposta qualquer") == "parcial"

    def test_limiar_de_parcial(self):
        assert situacao_por_nota(40, "resposta qualquer") == "parcial"
        assert situacao_por_nota(39, "resposta qualquer") == "lacuna"

    def test_resposta_vazia_e_lacuna_mesmo_com_nota_alta(self):
        assert situacao_por_nota(100, "") == "lacuna"
        assert situacao_por_nota(100, "   ") == "lacuna"


class TestRecomendacaoPorNota:
    def test_nota_alta_sem_lacunas_recomenda(self):
        assert recomendacao_por_nota(85, []) == "Recomendado para a próxima etapa do processo."

    def test_nota_alta_com_lacuna_vira_intermediaria(self):
        frase = recomendacao_por_nota(85, ["Visualização de dados"])
        assert frase.startswith("Aderência intermediária")

    def test_nota_media_e_intermediaria(self):
        assert recomendacao_por_nota(50, []).startswith("Aderência intermediária")

    def test_nota_baixa(self):
        assert recomendacao_por_nota(49, []) == "Aderência baixa aos requisitos desta vaga."


class TestAnalisarEntrevista:
    def _vaga(self) -> Vaga:
        return Vaga(
            titulo="Analista",
            competencias=[
                Competencia(nome="A", peso=3, palavras_chave=["alfa"]),
                Competencia(
                    nome="B", peso=1, palavras_chave=["sql", "join", "modelagem", "tabela"]
                ),
            ],
        )

    def _respostas(self) -> list[Resposta]:
        return [
            _resposta(None, "Minha trajetória começou no varejo.", tipo="abertura"),
            _resposta("A", ""),
            _resposta("B", RESPOSTA_RICA),
            _resposta(None, "Conversaria com a outra área.", tipo="situacional"),
        ]

    def test_nota_geral_e_ponderada_pelos_pesos(self):
        analise = analisar_entrevista(self._vaga(), self._respostas())

        notas = {a.competencia: a.nota for a in analise.avaliacoes}
        assert notas == {"A": 0, "B": 100}
        # (0 * 3 + 100 * 1) / (3 + 1) = 25 — a média simples daria 50.
        assert analise.nota_geral == 25

    def test_destaques_e_lacunas_derivam_da_situacao(self):
        analise = analisar_entrevista(self._vaga(), self._respostas())

        assert analise.destaques == ["B"]
        assert analise.lacunas == ["A"]
        assert "A: pergunta ficou sem resposta" in analise.riscos

    def test_recomendacao_e_metodo(self):
        analise = analisar_entrevista(self._vaga(), self._respostas())

        assert analise.recomendacao == "Aderência baixa aos requisitos desta vaga."
        assert analise.metodo == "heuristico"

    def test_perguntas_de_apoio_nao_entram_na_avaliacao(self):
        analise = analisar_entrevista(self._vaga(), self._respostas())
        assert [a.competencia for a in analise.avaliacoes] == ["A", "B"]

    def test_entrevista_sem_competencias_tem_nota_zero(self):
        vaga = Vaga(titulo="Vaga Enxuta")
        respostas = [_resposta(None, "Olá, tudo bem.", tipo="abertura")]

        analise = analisar_entrevista(vaga, respostas)

        assert analise.avaliacoes == []
        assert analise.nota_geral == 0
        assert analise.recomendacao == "Aderência baixa aos requisitos desta vaga."
