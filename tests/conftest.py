"""Fixtures compartilhadas da suíte de testes do iAuto.

Isolam a API de qualquer dependência externa: a transcrição (Whisper), a
análise por LLM (OpenRouter) e a síntese de voz (edge-tts) nunca rodam de
verdade — tudo é substituído por dublês locais, rápidos e determinísticos.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_DADOS = RAIZ_PROJETO / "dados"

TEXTO_TRANSCRITO = "texto transcrito de teste"


def _transcrever_falso(caminho_audio, tamanho_modelo="small", tempo_espera=120):
    """Dublê da transcrição: não toca no Whisper nem baixa modelo algum."""
    return TEXTO_TRANSCRITO


@pytest.fixture(autouse=True)
def ambiente_isolado(monkeypatch, tmp_path):
    """Reseta o contexto do processo e corta toda dependência externa.

    - o singleton ``contexto`` volta ao estado inicial entre testes;
    - toda escrita em disco vai para ``tmp_path`` (Windows e Linux);
    - ``transcrever``/``carregar_modelo`` viram dublês (sem download);
    - sem OPENROUTER_API_KEY, a análise sempre cai na heurística (sem rede).
    """
    from iauto.api import contexto as modulo_contexto
    from iauto.api import rotas_pipeline, rotas_sessao

    modulo_contexto.contexto.sessoes.clear()
    modulo_contexto.contexto.vaga = None
    modulo_contexto.contexto.candidato = None
    modulo_contexto.contexto.modelo = "tiny"

    # PASTA_SAIDA é um Path importado por valor em rotas_sessao: patch nos dois.
    monkeypatch.setattr(modulo_contexto, "PASTA_SAIDA", tmp_path)
    monkeypatch.setattr(rotas_sessao, "PASTA_SAIDA", tmp_path)

    # As rotas importam a função por nome: patch no namespace de cada módulo.
    monkeypatch.setattr(rotas_pipeline, "transcrever", _transcrever_falso)
    monkeypatch.setattr(rotas_sessao, "transcrever", _transcrever_falso)
    monkeypatch.setattr(rotas_sessao, "carregar_modelo", lambda tamanho="small": None)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    yield

    modulo_contexto.contexto.sessoes.clear()
    modulo_contexto.contexto.vaga = None
    modulo_contexto.contexto.candidato = None


@pytest.fixture
def client():
    """Cliente de teste da aplicação FastAPI do iAuto."""
    from iauto.api.app import app

    return TestClient(app)


def _carregar_json(nome: str) -> dict:
    with open(PASTA_DADOS / nome, encoding="utf-8") as arquivo:
        return json.load(arquivo)


@pytest.fixture
def vaga_json():
    """Vaga de exemplo real do projeto (4 competências, pesos 3/3/2/2)."""
    return _carregar_json("vaga_exemplo.json")


@pytest.fixture
def candidato_json():
    """Candidata de exemplo real do projeto (Maria Silva, 3 experiências)."""
    return _carregar_json("candidato_exemplo.json")
