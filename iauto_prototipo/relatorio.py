"""Geração do relatório por candidato, em Markdown e em JSON."""

import json
import os
from datetime import datetime


def _secao_lista(titulo, itens, vazio):
    linhas = ["", f"## {titulo}", ""]
    if itens:
        linhas.extend(f"- {item}" for item in itens)
    else:
        linhas.append(vazio)
    return linhas


def gerar_relatorio(vaga, candidato, respostas, analise, pasta_saida):
    agora = datetime.now()
    empresa = f" ({vaga['empresa']})" if vaga.get("empresa") else ""

    linhas = [
        "# Relatório de Entrevista Automatizada (iAuto)",
        "",
        f"Candidato: {candidato['nome']}  ",
        f"Vaga: {vaga['titulo']}{empresa}  ",
        f"Data: {agora.strftime('%d/%m/%Y %H:%M')}  ",
        f"Nota geral de aderência: **{analise['nota_geral']} / 100**  ",
        f"Recomendação: **{analise['recomendacao']}**",
        "",
        "## Aderência por competência",
        "",
        "| Competência | Peso | Nota | Situação | Termos identificados |",
        "|---|---|---|---|---|",
    ]
    for avaliacao in analise["avaliacoes"]:
        termos = ", ".join(avaliacao["termos_identificados"]) or "nenhum"
        linhas.append(
            f"| {avaliacao['competencia']} | {avaliacao['peso']} | "
            f"{avaliacao['nota']} | {avaliacao['situacao']} | {termos} |"
        )

    linhas += _secao_lista(
        "Destaques", analise["destaques"],
        "Nenhuma competência atingiu o nível de destaque.",
    )
    linhas += _secao_lista(
        "Riscos", analise["riscos"],
        "Nenhum risco relevante identificado nas respostas.",
    )
    linhas += _secao_lista(
        "Lacunas", analise["lacunas"],
        "Nenhuma lacuna identificada em relação às competências da vaga.",
    )

    linhas += ["", "## Trechos relevantes por competência", ""]
    for avaliacao in analise["avaliacoes"]:
        linhas.append(f"### {avaliacao['competencia']}")
        linhas.append("")
        if avaliacao["trechos_relevantes"]:
            for trecho in avaliacao["trechos_relevantes"]:
                linhas.append(f"> {trecho}")
                linhas.append("")
        else:
            linhas.append("Nenhum trecho diretamente ligado à competência foi identificado.")
            linhas.append("")

    linhas += ["## Transcrição completa", ""]
    for item in respostas:
        linhas.append(f"**Pergunta {item['id']}** ({item['tipo']}): {item['pergunta']}")
        linhas.append("")
        linhas.append(f"Resposta: {item.get('resposta') or '(sem resposta)'}")
        linhas.append("")

    caminho_md = os.path.join(pasta_saida, "relatorio.md")
    with open(caminho_md, "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas))

    dados = {
        "gerado_em": agora.isoformat(timespec="seconds"),
        "vaga": vaga["titulo"],
        "candidato": candidato["nome"],
        "analise": analise,
        "entrevista": respostas,
    }
    caminho_json = os.path.join(pasta_saida, "relatorio.json")
    with open(caminho_json, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)

    return caminho_md, caminho_json
