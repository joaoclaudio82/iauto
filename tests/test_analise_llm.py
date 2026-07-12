"""Testes da análise semântica com LLM (iauto.servicos.analise_llm).

Nenhum teste fala com a OpenRouter de verdade: o par (cliente, modelo) é
substituído com monkeypatch por dublês que devolvem conteúdo controlado ou
falham de propósito, para exercitar a validação e o fallback heurístico.
"""

import json
from types import SimpleNamespace

import pytest

from iauto.dominio.modelos import Competencia, Resposta, Vaga
from iauto.servicos import analise_llm
from iauto.servicos.analise_llm import analisar_com_fallback


class ClienteFalso:
    """Imita o cliente da OpenAI: chat.completions.create(**kw) -> resposta."""

    def __init__(self, conteudo: str):
        self._conteudo = conteudo
        self.chamadas = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        mensagem = SimpleNamespace(content=self._conteudo)
        return SimpleNamespace(choices=[SimpleNamespace(message=mensagem)])


class ClienteQueFalha:
    """Cliente cuja chamada sempre levanta erro (rede fora, chave inválida...)."""

    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        raise RuntimeError("rede indisponível (simulada)")


def _vaga() -> Vaga:
    return Vaga(
        titulo="Pessoa Desenvolvedora Python",
        empresa="Empresa Exemplo",
        competencias=[
            Competencia(nome="Python", peso=3, palavras_chave=["python", "pytest"]),
            Competencia(nome="SQL", peso=1, palavras_chave=["sql", "consultas"]),
        ],
    )


def _respostas() -> list[Resposta]:
    return [
        Resposta(id=1, tipo="abertura", pergunta="Fale sobre você.", resposta="Olá, sou a Maria."),
        Resposta(
            id=2,
            tipo="competencia",
            competencia="Python",
            pergunta="Conte sua experiência com Python.",
            resposta=(
                "Trabalho com python há cinco anos e implementei suítes de pytest "
                "em vários projetos, por exemplo em um sistema de faturamento que "
                "reduzi o tempo de deploy pela metade."
            ),
        ),
        Resposta(
            id=3,
            tipo="competencia",
            competencia="SQL",
            pergunta="E com bancos de dados?",
            resposta=(
                "Escrevo consultas sql complexas no dia a dia e otimizei relatórios "
                "lentos criando índices adequados no projeto anterior."
            ),
        ),
    ]


def _conteudo_llm(avaliacoes, recomendacao="Frase de recomendação do modelo."):
    return json.dumps({"avaliacoes": avaliacoes, "recomendacao": recomendacao}, ensure_ascii=False)


def _avaliacoes_padrao(
    nota_python=85, nota_sql=60, situacao_python="aderente", situacao_sql="parcial"
):
    return [
        {
            "competencia": "Python",
            "nota": nota_python,
            "situacao": situacao_python,
            "trechos_relevantes": ["implementei suítes de pytest"],
            "riscos": [],
        },
        {
            "competencia": "SQL",
            "nota": nota_sql,
            "situacao": situacao_sql,
            "trechos_relevantes": ["otimizei relatórios lentos"],
            "riscos": ["pouca menção a modelagem de dados"],
        },
    ]


def _instalar_cliente(monkeypatch, cliente, nome_modelo="modelo-teste"):
    monkeypatch.setattr(analise_llm, "_cliente_e_modelo", lambda: (cliente, nome_modelo))
    return cliente


# ---------------------------------------------------------------------------
# Fallback heurístico
# ---------------------------------------------------------------------------


def test_sem_configuracao_usa_heuristica(monkeypatch):
    """Sem OPENROUTER_API_KEY/OPENROUTER_MODEL a análise é a heurística."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "heuristico"
    assert analise.modelo_llm is None
    assert len(analise.avaliacoes) == 2


def test_falha_do_cliente_cai_na_heuristica_sem_propagar(monkeypatch):
    """Erro na chamada ao LLM não estoura para o chamador: cai na heurística."""
    _instalar_cliente(monkeypatch, ClienteQueFalha())

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "heuristico"


def test_competencia_faltando_na_resposta_cai_na_heuristica(monkeypatch):
    """Se o modelo esquece uma competência, a resposta inteira é descartada."""
    so_python = [_avaliacoes_padrao()[0]]
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(so_python)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "heuristico"


# ---------------------------------------------------------------------------
# Caminho feliz com o LLM
# ---------------------------------------------------------------------------


def test_json_canonico_devolve_analise_llm(monkeypatch):
    """JSON válido do modelo produz Analise com metodo='llm' e campos mapeados."""
    cliente = _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(_avaliacoes_padrao())))

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "llm"
    assert analise.modelo_llm == "modelo-teste"
    assert analise.recomendacao == "Frase de recomendação do modelo."
    assert cliente.chamadas[0]["model"] == "modelo-teste"

    # só as respostas de competência entram; abertura é ignorada
    assert [a.competencia for a in analise.avaliacoes] == ["Python", "SQL"]
    por_nome = {a.competencia: a for a in analise.avaliacoes}
    assert por_nome["Python"].nota == 85
    assert por_nome["Python"].peso == 3
    assert por_nome["Python"].trechos_relevantes == ["implementei suítes de pytest"]
    assert analise.riscos == ["SQL: pouca menção a modelagem de dados"]
    assert analise.destaques == ["Python"]
    assert analise.lacunas == []


def test_campos_objetivos_calculados_em_python(monkeypatch):
    """Termos, exemplo e contagem de palavras vêm da resposta, não do modelo."""
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(_avaliacoes_padrao())))

    analise = analisar_com_fallback(_vaga(), _respostas())

    python = next(a for a in analise.avaliacoes if a.competencia == "Python")
    assert set(python.termos_identificados) == {"python", "pytest"}
    assert python.tem_exemplo is True  # "por exemplo" / "implementei" na resposta
    assert python.n_palavras == len(_respostas()[1].resposta.split())


def test_nota_geral_e_media_ponderada_recalculada(monkeypatch):
    """A nota geral é recalculada em Python: (100*3 + 60*1) / 4 = 90."""
    avaliacoes = _avaliacoes_padrao(nota_python=100, nota_sql=60)
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "llm"
    assert analise.nota_geral == 90


# ---------------------------------------------------------------------------
# Saneamento do que vem do modelo
# ---------------------------------------------------------------------------


def test_nota_fora_da_faixa_e_clampada(monkeypatch):
    """Nota 150 vira 100 e nota negativa vira 0."""
    avaliacoes = _avaliacoes_padrao(nota_python=150, nota_sql=-20, situacao_sql="lacuna")
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    por_nome = {a.competencia: a for a in analise.avaliacoes}
    assert analise.metodo == "llm"
    assert por_nome["Python"].nota == 100
    assert por_nome["SQL"].nota == 0


def test_situacao_invalida_e_derivada_da_nota(monkeypatch):
    """Situação fora do vocabulário é substituída pela regra por nota."""
    avaliacoes = _avaliacoes_padrao(
        nota_python=90, situacao_python="excelente", nota_sql=50, situacao_sql=""
    )
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    por_nome = {a.competencia: a for a in analise.avaliacoes}
    assert por_nome["Python"].situacao == "aderente"  # nota 90 >= NOTA_ADERENTE
    assert por_nome["SQL"].situacao == "parcial"  # 40 <= nota 50 < 70


def test_trechos_relevantes_null_nao_quebra(monkeypatch):
    """trechos_relevantes/riscos null viram listas vazias, sem erro."""
    avaliacoes = _avaliacoes_padrao()
    avaliacoes[0]["trechos_relevantes"] = None
    avaliacoes[0]["riscos"] = None
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    python = next(a for a in analise.avaliacoes if a.competencia == "Python")
    assert analise.metodo == "llm"
    assert python.trechos_relevantes == []
    assert python.riscos == []


def test_trechos_relevantes_limitados_a_dois(monkeypatch):
    """Mesmo que o modelo mande quatro trechos, só os dois primeiros ficam."""
    avaliacoes = _avaliacoes_padrao()
    avaliacoes[0]["trechos_relevantes"] = ["um", "dois", "três", "quatro"]
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes)))

    analise = analisar_com_fallback(_vaga(), _respostas())

    python = next(a for a in analise.avaliacoes if a.competencia == "Python")
    assert python.trechos_relevantes == ["um", "dois"]


def test_recomendacao_vazia_e_derivada_da_nota(monkeypatch):
    """Sem recomendação do modelo, usa a frase padrão da regra por nota."""
    avaliacoes = _avaliacoes_padrao(nota_python=90, nota_sql=80, situacao_sql="aderente")
    _instalar_cliente(monkeypatch, ClienteFalso(_conteudo_llm(avaliacoes, recomendacao="  ")))

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "llm"
    assert analise.recomendacao == "Recomendado para a próxima etapa do processo."


# ---------------------------------------------------------------------------
# Tolerância no parse do JSON
# ---------------------------------------------------------------------------


def test_json_em_cerca_de_markdown_ainda_parseia(monkeypatch):
    """Modelo que embrulha o JSON em ```json ... ``` não derruba a análise."""
    conteudo = "```json\n" + _conteudo_llm(_avaliacoes_padrao()) + "\n```"
    _instalar_cliente(monkeypatch, ClienteFalso(conteudo))

    analise = analisar_com_fallback(_vaga(), _respostas())

    assert analise.metodo == "llm"


def test_extrair_json_tolera_texto_em_volta():
    """_extrair_json acha o objeto mesmo com prosa antes e depois."""
    texto = 'Claro! Aqui está a avaliação: {"chave": [1, 2]} Espero ter ajudado.'
    assert analise_llm._extrair_json(texto) == {"chave": [1, 2]}


def test_extrair_json_sem_json_levanta_erro():
    """Sem nenhum objeto JSON no texto, o erro de parse é propagado."""
    with pytest.raises(json.JSONDecodeError):
        analise_llm._extrair_json("não tem json nenhum aqui")
