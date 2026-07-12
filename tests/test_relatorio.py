"""Testes do relatório em Markdown e JSON (iauto.dominio.relatorio)."""

import json

import pytest

from iauto.dominio.analise import analisar_entrevista
from iauto.dominio.modelos import Candidato, Competencia, Resposta, Vaga
from iauto.dominio.relatorio import gerar_relatorio, montar_relatorio

RESPOSTA_COM_EXEMPLO = (
    "No projeto de vendas eu implementei consultas SQL com join e "
    "modelagem de tabela para o time comercial. "
    + "Depois disso acompanhei a evolucao dos numeros com o time toda semana. "
    * 6
)


@pytest.fixture()
def cenario():
    """Vaga, candidato, respostas e análise consistentes entre si."""
    vaga = Vaga(
        titulo="Analista de Dados Pleno",
        empresa="Empresa Exemplo",
        competencias=[
            Competencia(
                nome="SQL e modelagem de dados",
                peso=3,
                palavras_chave=["sql", "join", "modelagem", "tabela"],
            ),
            Competencia(
                nome="Visualização de dados",
                peso=2,
                palavras_chave=["dashboard", "painel"],
            ),
        ],
    )
    candidato = Candidato(nome="Maria Silva", resumo="Analista de dados.")
    respostas = [
        Resposta(
            id=1,
            tipo="abertura",
            pergunta="Fale sobre a sua trajetória.",
            resposta="Comecei como estagiária na área comercial.",
        ),
        Resposta(
            id=2,
            tipo="competencia",
            competencia="SQL e modelagem de dados",
            pergunta="Conte sobre a sua experiência com SQL.",
            resposta=RESPOSTA_COM_EXEMPLO,
        ),
        Resposta(
            id=3,
            tipo="competencia",
            competencia="Visualização de dados",
            pergunta="Conte sobre painéis que você construiu.",
            resposta="",
        ),
    ]
    analise = analisar_entrevista(vaga, respostas)
    return vaga, candidato, respostas, analise


class TestMontarRelatorio:
    def test_cabecalho_com_titulo_candidato_e_vaga(self, cenario):
        vaga, candidato, respostas, analise = cenario
        texto_md, _ = montar_relatorio(vaga, candidato, respostas, analise)

        assert texto_md.startswith("# Relatório de Entrevista Automatizada (iAuto)")
        assert "Candidato: Maria Silva" in texto_md
        assert "Vaga: Analista de Dados Pleno (Empresa Exemplo)" in texto_md
        assert f"Nota geral de aderência: **{analise.nota_geral} / 100**" in texto_md
        assert f"Recomendação: **{analise.recomendacao}**" in texto_md

    def test_vaga_sem_empresa_nao_mostra_parenteses(self, cenario):
        vaga, candidato, respostas, analise = cenario
        vaga_sem_empresa = vaga.model_copy(update={"empresa": ""})
        texto_md, _ = montar_relatorio(vaga_sem_empresa, candidato, respostas, analise)

        assert "Vaga: Analista de Dados Pleno  " in texto_md
        assert "(Empresa Exemplo)" not in texto_md

    def test_tabela_tem_uma_linha_por_competencia(self, cenario):
        vaga, candidato, respostas, analise = cenario
        texto_md, _ = montar_relatorio(vaga, candidato, respostas, analise)

        assert "| Competência | Peso | Nota | Situação | Termos identificados |" in texto_md
        for avaliacao in analise.avaliacoes:
            linha_esperada = (
                f"| {avaliacao.competencia} | {avaliacao.peso} | "
                f"{avaliacao.nota} | {avaliacao.situacao} |"
            )
            assert linha_esperada in texto_md
        # A competência sem resposta aparece com "nenhum" termo identificado.
        assert "| Visualização de dados | 2 | 0 | lacuna | nenhum |" in texto_md

    def test_secoes_de_destaques_riscos_e_lacunas(self, cenario):
        vaga, candidato, respostas, analise = cenario
        texto_md, _ = montar_relatorio(vaga, candidato, respostas, analise)

        assert "## Destaques" in texto_md
        assert "## Riscos" in texto_md
        assert "## Lacunas" in texto_md
        assert "- SQL e modelagem de dados" in texto_md
        assert "- Visualização de dados" in texto_md
        assert "- Visualização de dados: pergunta ficou sem resposta" in texto_md

    def test_transcricao_completa_com_todas_as_perguntas(self, cenario):
        vaga, candidato, respostas, analise = cenario
        texto_md, _ = montar_relatorio(vaga, candidato, respostas, analise)

        assert "## Transcrição completa" in texto_md
        for item in respostas:
            assert f"**Pergunta {item.id}** ({item.tipo}): {item.pergunta}" in texto_md
        assert "Resposta: Comecei como estagiária na área comercial." in texto_md
        # Pergunta sem resposta é marcada explicitamente.
        assert "Resposta: (sem resposta)" in texto_md

    def test_dados_json_tem_as_chaves_esperadas(self, cenario):
        vaga, candidato, respostas, analise = cenario
        _, dados = montar_relatorio(vaga, candidato, respostas, analise)

        assert set(dados) == {"gerado_em", "vaga", "candidato", "analise", "entrevista"}
        assert dados["vaga"] == "Analista de Dados Pleno"
        assert dados["candidato"] == "Maria Silva"
        assert dados["analise"]["nota_geral"] == analise.nota_geral
        assert len(dados["entrevista"]) == 3
        assert dados["entrevista"][1]["competencia"] == "SQL e modelagem de dados"

    def test_dados_json_sao_serializaveis(self, cenario):
        vaga, candidato, respostas, analise = cenario
        _, dados = montar_relatorio(vaga, candidato, respostas, analise)

        # model_dump precisa produzir estrutura serializável sem tipos exóticos.
        json.dumps(dados, ensure_ascii=False)


class TestGerarRelatorio:
    def test_grava_markdown_e_json_na_pasta_indicada(self, cenario, tmp_path):
        vaga, candidato, respostas, analise = cenario
        caminho_md, caminho_json = gerar_relatorio(
            vaga, candidato, respostas, analise, str(tmp_path)
        )

        assert caminho_md == str(tmp_path / "relatorio.md")
        assert caminho_json == str(tmp_path / "relatorio.json")
        assert (tmp_path / "relatorio.md").is_file()
        assert (tmp_path / "relatorio.json").is_file()

    def test_markdown_gravado_corresponde_ao_montado(self, cenario, tmp_path):
        vaga, candidato, respostas, analise = cenario
        caminho_md, _ = gerar_relatorio(vaga, candidato, respostas, analise, str(tmp_path))

        conteudo = (tmp_path / "relatorio.md").read_text(encoding="utf-8")
        assert conteudo.startswith("# Relatório de Entrevista Automatizada (iAuto)")
        assert "Candidato: Maria Silva" in conteudo
        assert "## Transcrição completa" in conteudo

    def test_json_recarrega_com_chaves_e_acentos_preservados(self, cenario, tmp_path):
        vaga, candidato, respostas, analise = cenario
        _, caminho_json = gerar_relatorio(vaga, candidato, respostas, analise, str(tmp_path))

        with open(caminho_json, encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        assert set(dados) == {"gerado_em", "vaga", "candidato", "analise", "entrevista"}
        assert dados["candidato"] == "Maria Silva"
        assert dados["analise"]["metodo"] == "heuristico"
        # ensure_ascii=False mantém os acentos legíveis no arquivo bruto.
        bruto = (tmp_path / "relatorio.json").read_text(encoding="utf-8")
        assert "Visualização de dados" in bruto
        assert "\\u00e7" not in bruto
