"""Testes do gerador de roteiro de entrevista (iauto.dominio.roteiro)."""

import json
from pathlib import Path

import pytest

from iauto.dominio.modelos import Candidato, Competencia, Vaga
from iauto.dominio.roteiro import gerar_roteiro, normalizar

PASTA_DADOS = Path(__file__).resolve().parents[1] / "dados"


def _carregar_exemplos() -> tuple[Vaga, Candidato]:
    """Carrega a vaga e o candidato de exemplo distribuídos em dados/."""
    vaga = Vaga.model_validate(
        json.loads((PASTA_DADOS / "vaga_exemplo.json").read_text(encoding="utf-8"))
    )
    candidato = Candidato.model_validate(
        json.loads((PASTA_DADOS / "candidato_exemplo.json").read_text(encoding="utf-8"))
    )
    return vaga, candidato


class TestNormalizar:
    """Normalização de texto usada nas comparações de termos."""

    def test_remove_acentos_e_baixa_caixa(self):
        assert normalizar("Comunicação") == "comunicacao"
        assert normalizar("ÍNDICE") == "indice"
        assert normalizar("Otimização de Consultas") == "otimizacao de consultas"

    def test_texto_nulo_vira_string_vazia(self):
        assert normalizar(None) == ""
        assert normalizar("") == ""

    def test_texto_sem_acento_permanece_igual(self):
        assert normalizar("sql") == "sql"


class TestRoteiroComDadosDeExemplo:
    """Roteiro gerado a partir dos arquivos reais de dados/."""

    @pytest.fixture()
    def roteiro(self):
        vaga, candidato = _carregar_exemplos()
        return gerar_roteiro(vaga, candidato)

    def test_tem_sete_perguntas(self, roteiro):
        assert len(roteiro) == 7

    def test_estrutura_de_tipos(self, roteiro):
        tipos = [p.tipo for p in roteiro]
        assert tipos == [
            "abertura",
            "competencia",
            "competencia",
            "competencia",
            "competencia",
            "situacional",
            "encerramento",
        ]

    def test_ids_sequenciais_a_partir_de_um(self, roteiro):
        assert [p.id for p in roteiro] == list(range(1, 8))

    def test_abertura_cita_primeiro_nome_e_titulo_da_vaga(self, roteiro):
        abertura = roteiro[0]
        assert "Maria" in abertura.pergunta
        # Não deve usar o nome completo na saudação, apenas o primeiro nome.
        assert "Maria Silva" not in abertura.pergunta
        assert "Analista de Dados Pleno" in abertura.pergunta

    def test_perguntas_de_competencia_carregam_o_nome_da_competencia(self, roteiro):
        vaga, _ = _carregar_exemplos()
        nomes_esperados = [c.nome for c in vaga.competencias]
        nomes_no_roteiro = [p.competencia for p in roteiro if p.tipo == "competencia"]
        assert nomes_no_roteiro == nomes_esperados

    def test_pergunta_personalizada_cita_experiencia_do_curriculo(self, roteiro):
        """A competência de SQL casa com a experiência de consultas SQL do currículo."""
        pergunta_sql = next(p for p in roteiro if p.competencia == "SQL e modelagem de dados")
        assert "Consultas SQL em bases com milhões de registros" in pergunta_sql.pergunta
        assert "No seu currículo consta" in pergunta_sql.pergunta

    def test_perguntas_de_apoio_nao_tem_competencia(self, roteiro):
        for pergunta in roteiro:
            if pergunta.tipo != "competencia":
                assert pergunta.competencia is None


class TestPersonalizacaoDoRoteiro:
    """Escolha entre pergunta personalizada e genérica por competência."""

    def _candidato(self, experiencias: list[str]) -> Candidato:
        return Candidato(nome="João Souza", experiencias=experiencias)

    def _vaga(self, competencia: Competencia) -> Vaga:
        return Vaga(titulo="Vaga Teste", competencias=[competencia])

    def test_sem_palavra_chave_no_curriculo_usa_pergunta_generica(self):
        vaga = self._vaga(
            Competencia(nome="Gestão de projetos", palavras_chave=["scrum", "kanban"])
        )
        candidato = self._candidato(["Atendimento ao cliente em loja física"])

        roteiro = gerar_roteiro(vaga, candidato)
        pergunta = next(p for p in roteiro if p.tipo == "competencia")

        assert pergunta.pergunta.startswith("Descreva uma situação real")
        assert "Gestão de projetos" in pergunta.pergunta
        assert "No seu currículo consta" not in pergunta.pergunta

    def test_palavra_chave_casa_mesmo_com_acentuacao_diferente(self):
        """Termo sem acento na vaga encontra experiência acentuada no currículo."""
        vaga = self._vaga(Competencia(nome="Automação de processos", palavras_chave=["automacao"]))
        experiencia = "Automação de relatórios financeiros mensais"
        candidato = self._candidato([experiencia])

        roteiro = gerar_roteiro(vaga, candidato)
        pergunta = next(p for p in roteiro if p.tipo == "competencia")

        assert experiencia in pergunta.pergunta
        assert "No seu currículo consta" in pergunta.pergunta

    def test_usa_a_primeira_experiencia_que_casa(self):
        vaga = self._vaga(Competencia(nome="Python", palavras_chave=["python"]))
        candidato = self._candidato(
            [
                "Scripts Python para carga de dados",
                "Outra atuação com Python em análise",
            ]
        )

        roteiro = gerar_roteiro(vaga, candidato)
        pergunta = next(p for p in roteiro if p.tipo == "competencia")

        assert "Scripts Python para carga de dados" in pergunta.pergunta

    def test_vaga_sem_competencias_gera_so_perguntas_fixas(self):
        vaga = Vaga(titulo="Vaga Enxuta")
        candidato = self._candidato([])

        roteiro = gerar_roteiro(vaga, candidato)

        assert [p.tipo for p in roteiro] == ["abertura", "situacional", "encerramento"]
        assert [p.id for p in roteiro] == [1, 2, 3]
