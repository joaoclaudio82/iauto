"""Protótipo iAuto: entrevista de emprego automatizada por áudio, em português.

Fluxo: roteiro personalizado -> pergunta por voz -> gravação com cronômetro ->
transcrição ASR (Transformer) -> normalização e trechos relevantes ->
aderência por competência -> relatório por candidato.

Modos de execução:
  --modo audio     entrevista ao vivo com voz (microfone e alto-falante)
  --modo lote      processa áudios já gravados (fluxo assíncrono, estilo WhatsApp)
  --modo simulado  respostas digitadas, para testar o fluxo sem dependências de áudio
"""

import argparse
import glob
import json
import os
from datetime import datetime

from analise import analisar_entrevista
from relatorio import gerar_relatorio
from roteiro import gerar_roteiro

EXTENSOES_AUDIO = ("*.wav", "*.mp3", "*.ogg", "*.opus", "*.m4a")


def carregar_json(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


def criar_pasta_saida(candidato, base="saida"):
    carimbo = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    nome = candidato["nome"].split()[0].lower()
    pasta = os.path.join(base, f"{carimbo}_{nome}")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def entrevista_simulada(roteiro):
    """Fluxo de teste: as respostas são digitadas no lugar da fala."""
    respostas = []
    for item in roteiro:
        print("\n" + "=" * 70)
        print(f"[PERGUNTA {item['id']}] {item['pergunta']}")
        try:
            texto = input("[RESPOSTA digitada] > ").strip()
        except EOFError:
            texto = ""
        item = dict(item)
        item["resposta"] = texto
        respostas.append(item)
    return respostas


def entrevista_audio(roteiro, pasta_saida, tamanho_modelo, tempo_padrao=None):
    """Entrevista ao vivo: fala a pergunta, grava com cronômetro e transcreve."""
    from audio_io import falar, gravar_resposta
    from transcricao import carregar_modelo, transcrever

    carregar_modelo(tamanho_modelo)  # carrega antes, para não atrasar a primeira resposta
    respostas = []
    for item in roteiro:
        print("\n" + "=" * 70)
        print(f"[PERGUNTA {item['id']}] {item['pergunta']}")
        falar(item["pergunta"])
        tempo = tempo_padrao or item["tempo_max"]
        caminho = os.path.join(pasta_saida, f"resposta_{item['id']:02d}.wav")
        gravar_resposta(caminho, tempo_max=tempo)
        texto = transcrever(caminho, tamanho_modelo)
        print(f"[TRANSCRIÇÃO] {texto if texto else '(vazio)'}")
        item = dict(item)
        item["resposta"] = texto
        item["arquivo_audio"] = caminho
        respostas.append(item)
    return respostas


def entrevista_lote(roteiro, pasta_audios, tamanho_modelo):
    """Fluxo assíncrono: transcreve áudios já enviados (por exemplo, via WhatsApp)."""
    from transcricao import carregar_modelo, transcrever

    arquivos = []
    for extensao in EXTENSOES_AUDIO:
        arquivos.extend(glob.glob(os.path.join(pasta_audios, extensao)))
    arquivos = sorted(arquivos)
    if not arquivos:
        raise SystemExit(f"Nenhum áudio encontrado em: {pasta_audios}")
    if len(arquivos) != len(roteiro):
        print(
            f"[AVISO] O roteiro tem {len(roteiro)} perguntas e a pasta tem "
            f"{len(arquivos)} áudios. O pareamento segue a ordem alfabética dos arquivos."
        )

    carregar_modelo(tamanho_modelo)
    respostas = []
    for indice, item in enumerate(roteiro):
        item = dict(item)
        if indice < len(arquivos):
            caminho = arquivos[indice]
            print(f"[TRANSCREVENDO] pergunta {item['id']} <- {os.path.basename(caminho)}")
            item["resposta"] = transcrever(caminho, tamanho_modelo)
            item["arquivo_audio"] = caminho
        else:
            item["resposta"] = ""
        respostas.append(item)
    return respostas


def principal():
    parser = argparse.ArgumentParser(
        description="Protótipo iAuto de entrevista automatizada por áudio (PT-BR)"
    )
    parser.add_argument("--vaga", default="dados/vaga_exemplo.json")
    parser.add_argument("--candidato", default="dados/candidato_exemplo.json")
    parser.add_argument("--modo", choices=["audio", "lote", "simulado"], default="simulado")
    parser.add_argument("--audios", help="pasta com os áudios das respostas (modo lote)")
    parser.add_argument(
        "--modelo", default="small",
        help="tamanho do modelo ASR: tiny, base, small ou medium",
    )
    parser.add_argument(
        "--tempo", type=int,
        help="tempo máximo por resposta, em segundos (modo audio)",
    )
    args = parser.parse_args()

    vaga = carregar_json(args.vaga)
    candidato = carregar_json(args.candidato)
    pasta_saida = criar_pasta_saida(candidato)

    roteiro = gerar_roteiro(vaga, candidato)
    print(
        f"[iAuto] Roteiro gerado com {len(roteiro)} perguntas para "
        f"{candidato['nome']} (vaga: {vaga['titulo']})."
    )

    if args.modo == "audio":
        respostas = entrevista_audio(roteiro, pasta_saida, args.modelo, args.tempo)
    elif args.modo == "lote":
        if not args.audios:
            raise SystemExit("Informe --audios com a pasta dos arquivos de resposta.")
        respostas = entrevista_lote(roteiro, args.audios, args.modelo)
    else:
        respostas = entrevista_simulada(roteiro)

    analise = analisar_entrevista(vaga, respostas)
    caminho_md, caminho_json = gerar_relatorio(vaga, candidato, respostas, analise, pasta_saida)

    print("\n" + "=" * 70)
    print(f"[iAuto] Nota geral de aderência: {analise['nota_geral']} / 100")
    print(f"[iAuto] {analise['recomendacao']}")
    print(f"[iAuto] Relatório salvo em: {caminho_md}")
    print(f"[iAuto] Dados completos em: {caminho_json}")


if __name__ == "__main__":
    principal()
