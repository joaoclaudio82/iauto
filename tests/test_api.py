"""Testes da API HTTP do iAuto (rotas do pipeline e da entrevista web).

Usa TestClient sobre a aplicação real; transcrição, LLM e voz neural são
dublês definidos no conftest — nenhum teste toca rede ou baixa modelo.
"""

import json

# Mesmo texto devolvido pelo dublê de transcrição do conftest.
TEXTO_TRANSCRITO = "texto transcrito de teste"

TAMANHOS_ASR = ("tiny", "base", "small", "medium")

RESPOSTA_LONGA = (
    "Por exemplo, no varejo trabalhei bastante com sql, python e dashboard, "
    "otimizando consultas e apresentando resultados para a área de negócio "
    "com indicadores claros medidos em produção."
)


def _respostas_competencia(vaga_json: dict) -> list[dict]:
    """Uma resposta de competência para cada competência da vaga de exemplo."""
    return [
        {
            "id": indice,
            "tipo": "competencia",
            "competencia": competencia["nome"],
            "pergunta": f"Fale sobre {competencia['nome']}.",
            "resposta": RESPOSTA_LONGA,
        }
        for indice, competencia in enumerate(vaga_json["competencias"], start=2)
    ]


# ---------------------------------------------------------------- página e info


def test_pagina_inicial_devolve_html(client):
    """GET / serve a interface web como HTML."""
    resposta = client.get("/")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert resposta.text.strip()


def test_api_info_traz_vaga_e_candidato(client):
    """GET /api/info carrega a configuração padrão e expõe vaga e candidato."""
    resposta = client.get("/api/info")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["vaga"]["titulo"] == "Analista de Dados Pleno"
    assert dados["candidato"]["nome"] == "Maria Silva"
    assert dados["modelo_asr"]


# -------------------------------------------------------------- /api/v1/roteiro


def test_roteiro_gera_sete_perguntas(client, vaga_json, candidato_json):
    """O roteiro do par de exemplo tem 7 perguntas na estrutura esperada."""
    resposta = client.post("/api/v1/roteiro", json={"vaga": vaga_json, "candidato": candidato_json})
    assert resposta.status_code == 200
    perguntas = resposta.json()["perguntas"]
    assert len(perguntas) == 7
    tipos = [p["tipo"] for p in perguntas]
    assert tipos[0] == "abertura"
    assert tipos[-1] == "encerramento"
    assert tipos.count("competencia") == 4
    assert tipos.count("situacional") == 1


def test_roteiro_nome_em_branco_da_422(client, vaga_json, candidato_json):
    """Candidato com nome só de espaços é rejeitado na validação (422)."""
    candidato_json["nome"] = "   "
    resposta = client.post("/api/v1/roteiro", json={"vaga": vaga_json, "candidato": candidato_json})
    assert resposta.status_code == 422


# -------------------------------------------------------------- /api/v1/analise


def test_analise_heuristica(client, vaga_json):
    """Sem OPENROUTER configurado a análise usa a heurística do domínio."""
    resposta = client.post(
        "/api/v1/analise",
        json={"vaga": vaga_json, "respostas": _respostas_competencia(vaga_json)},
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["metodo"] == "heuristico"
    assert 0 <= dados["nota_geral"] <= 100
    assert len(dados["avaliacoes"]) == 4
    nomes = {a["competencia"] for a in dados["avaliacoes"]}
    assert nomes == {c["nome"] for c in vaga_json["competencias"]}


def test_analise_competencia_desconhecida_da_422(client, vaga_json):
    """Resposta citando competência que não existe na vaga é rejeitada."""
    respostas = _respostas_competencia(vaga_json)
    respostas[0]["competencia"] = "Alquimia avançada"
    resposta = client.post("/api/v1/analise", json={"vaga": vaga_json, "respostas": respostas})
    assert resposta.status_code == 422
    assert "Alquimia avançada" in resposta.json()["detail"]


def test_analise_competencia_duplicada_da_422(client, vaga_json):
    """Duas respostas para a mesma competência contariam o peso em dobro."""
    respostas = _respostas_competencia(vaga_json)
    duplicada = dict(respostas[0], id=99)
    resposta = client.post(
        "/api/v1/analise",
        json={"vaga": vaga_json, "respostas": respostas + [duplicada]},
    )
    assert resposta.status_code == 422


# ------------------------------------------------------------ /api/v1/relatorio


def test_relatorio_com_analise_da_rota(client, vaga_json, candidato_json):
    """O relatório aceita a análise devolvida pela própria rota de análise."""
    respostas = _respostas_competencia(vaga_json)
    analise = client.post(
        "/api/v1/analise", json={"vaga": vaga_json, "respostas": respostas}
    ).json()

    resposta = client.post(
        "/api/v1/relatorio",
        json={
            "vaga": vaga_json,
            "candidato": candidato_json,
            "respostas": respostas,
            "analise": analise,
        },
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert "Maria Silva" in dados["relatorio_md"]
    assert dados["relatorio_json"]["candidato"] == "Maria Silva"
    assert dados["relatorio_json"]["analise"]["metodo"] == "heuristico"


def test_relatorio_analise_vazia_da_422(client, vaga_json, candidato_json):
    """Análise sem os campos obrigatórios é rejeitada na validação."""
    resposta = client.post(
        "/api/v1/relatorio",
        json={
            "vaga": vaga_json,
            "candidato": candidato_json,
            "respostas": [],
            "analise": {},
        },
    )
    assert resposta.status_code == 422


# ----------------------------------------------------------- /api/v1/transcricao


def test_transcricao_multipart_usa_stub(client):
    """A rota devolve o texto do dublê e um modelo válido de ASR."""
    resposta = client.post(
        "/api/v1/transcricao",
        files={"audio": ("r.wav", b"bytes-quaisquer", "audio/wav")},
    )
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["texto"] == TEXTO_TRANSCRITO
    assert dados["modelo"] in TAMANHOS_ASR


def test_transcricao_modelo_tiny_explicito(client):
    """Modelo pedido explicitamente é aceito e ecoado na resposta."""
    resposta = client.post(
        "/api/v1/transcricao",
        files={"audio": ("r.wav", b"bytes-quaisquer", "audio/wav")},
        data={"modelo": "tiny"},
    )
    assert resposta.status_code == 200
    assert resposta.json()["modelo"] == "tiny"


def test_transcricao_modelo_invalido_da_422(client):
    """Tamanho de modelo desconhecido é rejeitado antes de transcrever."""
    resposta = client.post(
        "/api/v1/transcricao",
        files={"audio": ("r.wav", b"bytes-quaisquer", "audio/wav")},
        data={"modelo": "gigante"},
    )
    assert resposta.status_code == 422


def test_transcricao_asr_ocupado_da_503(client, monkeypatch):
    """AsrOcupadoErro no serviço vira 503 para o chamador tentar de novo."""
    from iauto.api import rotas_pipeline
    from iauto.servicos.transcricao import AsrOcupadoErro

    def _ocupado(caminho_audio, tamanho_modelo="small", tempo_espera=120):
        raise AsrOcupadoErro("ocupado")

    monkeypatch.setattr(rotas_pipeline, "transcrever", _ocupado)
    resposta = client.post(
        "/api/v1/transcricao",
        files={"audio": ("r.wav", b"bytes-quaisquer", "audio/wav")},
        data={"modelo": "tiny"},
    )
    assert resposta.status_code == 503


# ------------------------------------------------------- fluxo da entrevista web


def test_fluxo_de_sessao_completo(client):
    """Sessão de ponta a ponta: criar, responder (texto e áudio) e finalizar."""
    criada = client.post("/api/sessao")
    assert criada.status_code == 200
    dados = criada.json()
    sessao_id = dados["sessao_id"]
    perguntas = dados["perguntas"]
    assert sessao_id
    assert len(perguntas) == 7
    assert dados["candidato"] == "Maria Silva"

    # resposta por texto (form)
    id_texto = perguntas[0]["id"]
    resposta = client.post(
        f"/api/sessao/{sessao_id}/resposta/{id_texto}",
        data={"texto": "Sou analista de dados há quatro anos."},
    )
    assert resposta.status_code == 200
    assert resposta.json() == {
        "pergunta_id": id_texto,
        "transcricao": "Sou analista de dados há quatro anos.",
    }

    # resposta por áudio (multipart) usa o dublê de transcrição
    id_audio = perguntas[1]["id"]
    resposta = client.post(
        f"/api/sessao/{sessao_id}/resposta/{id_audio}",
        files={"audio": ("resposta.wav", b"RIFFfalso", "audio/wav")},
    )
    assert resposta.status_code == 200
    assert resposta.json()["transcricao"] == TEXTO_TRANSCRITO

    # finalizar: perguntas não respondidas viram resposta vazia
    final = client.post(f"/api/sessao/{sessao_id}/finalizar")
    assert final.status_code == 200
    dados = final.json()
    assert dados["analise"]["metodo"] == "heuristico"
    assert len(dados["respostas"]) == 7
    por_id = {r["id"]: r for r in dados["respostas"]}
    assert por_id[id_audio]["resposta"] == TEXTO_TRANSCRITO
    faltantes = [p["id"] for p in perguntas if p["id"] not in (id_texto, id_audio)]
    assert all(por_id[i]["resposta"] == "" for i in faltantes)
    assert dados["relatorio_md"].strip()

    # download dos arquivos gerados
    baixado_md = client.get(f"/api/sessao/{sessao_id}/arquivo/md")
    assert baixado_md.status_code == 200
    assert "Maria Silva" in baixado_md.content.decode("utf-8")

    baixado_json = client.get(f"/api/sessao/{sessao_id}/arquivo/json")
    assert baixado_json.status_code == 200
    assert json.loads(baixado_json.content.decode("utf-8"))["candidato"] == "Maria Silva"


def test_arquivo_antes_de_finalizar_da_404(client):
    """Sem finalizar a sessão não há relatório para baixar."""
    sessao_id = client.post("/api/sessao").json()["sessao_id"]
    assert client.get(f"/api/sessao/{sessao_id}/arquivo/md").status_code == 404
    assert client.get(f"/api/sessao/{sessao_id}/arquivo/json").status_code == 404


def test_sessao_inexistente_da_404(client):
    """Rotas de sessão com id desconhecido devolvem 404."""
    assert client.post("/api/sessao/nao-existe/resposta/1", data={"texto": "oi"}).status_code == 404
    assert client.post("/api/sessao/nao-existe/finalizar").status_code == 404


def test_arquivo_de_tipo_invalido_da_404(client):
    """Tipo de arquivo diferente de md/json devolve 404 mesmo após finalizar."""
    sessao_id = client.post("/api/sessao").json()["sessao_id"]
    assert client.post(f"/api/sessao/{sessao_id}/finalizar").status_code == 200
    assert client.get(f"/api/sessao/{sessao_id}/arquivo/xml").status_code == 404


# --------------------------------------------------------------------- /api/tts


def test_tts_devolve_audio_do_dube(client, monkeypatch):
    """GET /api/tts responde audio/mpeg com os bytes do dublê assíncrono."""
    from iauto.api import rotas_sessao

    async def _sintetizar_falso(texto, voz="qualquer"):
        return b"mp3"

    monkeypatch.setattr(rotas_sessao.tts, "sintetizar", _sintetizar_falso)
    resposta = client.get("/api/tts", params={"texto": "Olá, candidata!"})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("audio/mpeg")
    assert resposta.content == b"mp3"


def test_tts_texto_vazio_da_400(client):
    """Texto vazio é rejeitado antes de qualquer síntese (sem rede)."""
    resposta = client.get("/api/tts", params={"texto": "   "})
    assert resposta.status_code == 400
