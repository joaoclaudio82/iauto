"""Servidor web do protótipo iAuto: entrevista automatizada no navegador.

Reaproveita os módulos do CLI (roteiro, transcricao, analise, relatorio):
o navegador exibe e fala as perguntas (TTS do próprio browser), grava as
respostas pelo microfone (MediaRecorder) e envia os áudios; o servidor
transcreve com o Whisper local e devolve o relatório de aderência.

Execução:
  pip install fastapi uvicorn python-multipart
  python servidor.py --porta 8123
"""

import argparse
import json
import os
import threading
import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from analise import analisar_entrevista
from relatorio import gerar_relatorio
from roteiro import gerar_roteiro

RAIZ = os.path.dirname(os.path.abspath(__file__))
CAMINHO_INDEX = os.path.join(RAIZ, "web", "index.html")

EXTENSAO_POR_TIPO = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
}

app = FastAPI(title="iAuto — Entrevista Automatizada")

_sessoes = {}
_trava_asr = threading.Lock()
_config = {"vaga": None, "candidato": None, "modelo": "tiny"}


def _carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def _criar_pasta_saida(candidato):
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    nome = candidato["nome"].split()[0].lower()
    pasta = os.path.join(RAIZ, "saida", f"{carimbo}_{nome}_web")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _escolher_modelo(preferido="small", reserva="tiny"):
    """Usa o modelo preferido se já estiver no cache local; senão, o reserva."""
    base = os.environ.get(
        "HF_HOME", os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
    )
    pasta = os.path.join(base, "hub", f"models--Systran--faster-whisper-{preferido}")
    for _raiz, _dirs, arquivos in os.walk(pasta):
        if "model.bin" in arquivos:
            return preferido
    return reserva


def _carregar_asr():
    """Pré-carrega o modelo ASR para a primeira transcrição não esperar."""
    from transcricao import carregar_modelo

    with _trava_asr:
        try:
            carregar_modelo(_config["modelo"])
        except Exception as erro:
            print(f"[iAuto] Falha ao carregar o modelo ASR: {erro}")


@app.get("/")
def pagina():
    if not os.path.exists(CAMINHO_INDEX):
        raise HTTPException(500, "Interface web não encontrada (web/index.html).")
    return FileResponse(CAMINHO_INDEX, media_type="text/html")


@app.get("/api/info")
def informacoes():
    return {
        "vaga": _config["vaga"],
        "candidato": _config["candidato"],
        "modelo_asr": _config["modelo"],
    }


@app.post("/api/sessao")
def criar_sessao():
    vaga, candidato = _config["vaga"], _config["candidato"]
    roteiro = gerar_roteiro(vaga, candidato)
    sessao_id = uuid.uuid4().hex[:12]
    _sessoes[sessao_id] = {
        "vaga": vaga,
        "candidato": candidato,
        "roteiro": roteiro,
        "respostas": {},
        "pasta": _criar_pasta_saida(candidato),
        "finalizada": None,
    }
    threading.Thread(target=_carregar_asr, daemon=True).start()
    return {
        "sessao_id": sessao_id,
        "candidato": candidato["nome"],
        "vaga": vaga["titulo"],
        "empresa": vaga.get("empresa", ""),
        "modelo_asr": _config["modelo"],
        "perguntas": roteiro,
    }


@app.post("/api/sessao/{sessao_id}/resposta/{pergunta_id}")
def receber_resposta(
    sessao_id: str,
    pergunta_id: int,
    audio: UploadFile = File(None),
    texto: str = Form(None),
):
    sessao = _sessoes.get(sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada.")
    item = next((dict(p) for p in sessao["roteiro"] if p["id"] == pergunta_id), None)
    if not item:
        raise HTTPException(404, "Pergunta não encontrada.")

    if audio is not None and (audio.filename or audio.content_type):
        extensao = os.path.splitext(audio.filename or "")[1].lower()
        if not extensao:
            extensao = EXTENSAO_POR_TIPO.get(audio.content_type, ".webm")
        caminho = os.path.join(sessao["pasta"], f"resposta_{pergunta_id:02d}{extensao}")
        with open(caminho, "wb") as destino:
            destino.write(audio.file.read())
        item["arquivo_audio"] = caminho

        from transcricao import transcrever

        with _trava_asr:
            try:
                item["resposta"] = transcrever(caminho, _config["modelo"])
            except Exception as erro:
                raise HTTPException(500, f"Falha na transcrição: {erro}")
    else:
        item["resposta"] = (texto or "").strip()

    sessao["respostas"][pergunta_id] = item
    return {"pergunta_id": pergunta_id, "transcricao": item["resposta"]}


@app.post("/api/sessao/{sessao_id}/finalizar")
def finalizar(sessao_id: str):
    sessao = _sessoes.get(sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada.")

    respostas = []
    for pergunta in sessao["roteiro"]:
        item = sessao["respostas"].get(pergunta["id"]) or dict(pergunta)
        item.setdefault("resposta", "")
        respostas.append(item)

    analise = analisar_entrevista(sessao["vaga"], respostas)
    caminho_md, caminho_json = gerar_relatorio(
        sessao["vaga"], sessao["candidato"], respostas, analise, sessao["pasta"]
    )
    with open(caminho_md, encoding="utf-8") as arquivo:
        conteudo_md = arquivo.read()

    resultado = {
        "sessao_id": sessao_id,
        "candidato": sessao["candidato"]["nome"],
        "vaga": sessao["vaga"]["titulo"],
        "empresa": sessao["vaga"].get("empresa", ""),
        "analise": analise,
        "respostas": respostas,
        "caminho_md": caminho_md,
        "caminho_json": caminho_json,
        "relatorio_md": conteudo_md,
    }
    sessao["finalizada"] = resultado
    return resultado


@app.get("/api/sessao/{sessao_id}/arquivo/{tipo}")
def baixar_arquivo(sessao_id: str, tipo: str):
    sessao = _sessoes.get(sessao_id)
    if not sessao or not sessao["finalizada"]:
        raise HTTPException(404, "Relatório ainda não gerado para esta sessão.")
    if tipo == "md":
        return FileResponse(sessao["finalizada"]["caminho_md"], filename="relatorio.md")
    if tipo == "json":
        return FileResponse(
            sessao["finalizada"]["caminho_json"], filename="relatorio.json"
        )
    raise HTTPException(404, "Tipo de arquivo inválido (use md ou json).")


def _carregar_configuracao(caminho_vaga=None, caminho_candidato=None, modelo="auto"):
    _config["vaga"] = _carregar_json(
        caminho_vaga or os.path.join(RAIZ, "dados", "vaga_exemplo.json")
    )
    _config["candidato"] = _carregar_json(
        caminho_candidato or os.path.join(RAIZ, "dados", "candidato_exemplo.json")
    )
    _config["modelo"] = _escolher_modelo() if modelo == "auto" else modelo


# Configuração padrão no import, para `uvicorn servidor:app` também funcionar.
_carregar_configuracao()


def principal():
    parser = argparse.ArgumentParser(description="Servidor web do protótipo iAuto")
    parser.add_argument("--vaga", help="arquivo JSON da vaga")
    parser.add_argument("--candidato", help="arquivo JSON do candidato")
    parser.add_argument(
        "--modelo", default=os.environ.get("MODELO_ASR", "auto"),
        help="tiny, base, small, medium ou auto (small se já baixado)",
    )
    parser.add_argument(
        "--porta", type=int, default=int(os.environ.get("PORT", "8123")),
        help="porta HTTP (padrão: variável PORT ou 8123)",
    )
    parser.add_argument(
        "--host", default=os.environ.get("HOST", "127.0.0.1"),
        help="endereço de escuta (use 0.0.0.0 em deploy)",
    )
    args = parser.parse_args()

    _carregar_configuracao(args.vaga, args.candidato, args.modelo)
    print(f"[iAuto] Modelo ASR: {_config['modelo']}")
    print(f"[iAuto] Escutando em http://{args.host}:{args.porta}")
    uvicorn.run(app, host=args.host, port=args.porta)


if __name__ == "__main__":
    principal()
