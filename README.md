# iAuto — entrevista de emprego automatizada por áudio (PT-BR)

[![CI](https://github.com/joaoclaudio82/iauto/actions/workflows/ci.yml/badge.svg)](https://github.com/joaoclaudio82/iauto/actions/workflows/ci.yml)

Serviço de entrevista automatizada em português: gera um roteiro personalizado a partir da vaga e do currículo, faz as perguntas por voz, grava e transcreve as respostas localmente (Whisper) e produz um relatório de aderência por competência — pela interface web, pelo terminal ou por API para integração com outros sistemas.

## Arquitetura

```
iauto/
├── dominio/     # regras de negócio puras, sem I/O
│   ├── modelos.py      # Vaga, Candidato, Pergunta, Resposta, Analise (Pydantic)
│   ├── roteiro.py      # correlação vaga x currículo -> perguntas personalizadas
│   ├── analise.py      # aderência heurística por competência
│   └── relatorio.py    # relatório em Markdown/JSON
├── servicos/    # adaptadores de infraestrutura
│   ├── transcricao.py  # ASR local (faster-whisper, CPU)
│   ├── analise_llm.py  # análise semântica via OpenRouter, com fallback
│   └── tts.py          # voz neural do entrevistador (edge-tts)
├── api/         # FastAPI: entrevista web (com sessão) + pipeline sem estado
└── cli/         # entrevista pelo terminal (audio | lote | simulado)
web/             # interface da entrevista no navegador (SPA autocontida)
dados/           # vaga e candidato de exemplo (JSON)
tests/           # suíte pytest (domínio, serviços e API)
```

O domínio não conhece infraestrutura nem HTTP; API e CLI são cascas finas sobre as mesmas funções.

## Instalação

Requer Python 3.10+.

```bash
# serviço web / API / desenvolvimento
pip install -e ".[dev]"

# com o modo de entrevista ao vivo pelo terminal (microfone local)
pip install -e ".[audio,dev]"
```

Observações: no Linux, o modo de áudio ao vivo pede `sudo apt install libportaudio2 espeak-ng`. Na primeira transcrição, o modelo ASR é baixado automaticamente (o `small` tem ~460 MB; o `tiny`, ~75 MB).

## Como executar

```bash
# Interface web (http://127.0.0.1:8123)
python -m iauto.api

# Entrevista pelo terminal
python -m iauto.cli --modo simulado          # respostas digitadas, sem áudio
python -m iauto.cli --modo audio             # ao vivo, com microfone
python -m iauto.cli --modo lote --audios dir # transcreve áudios já enviados

# Testes e lint
pytest
ruff check .
```

Parâmetros úteis (web e CLI): `--vaga` e `--candidato` apontam para outros JSONs; `--modelo` escolhe o tamanho do ASR (`tiny`, `base`, `small`, `medium` ou `auto`). A saída de cada entrevista fica em `saida/<data>_<candidato>/` (a pasta `saida_exemplo/` traz um relatório pronto).

### Interface web

A pergunta é exibida e falada (voz neural com fallback para a voz do navegador), um cronômetro em anel marca o tempo, a resposta é gravada pelo microfone (waveform ao vivo) e transcrita no servidor. No final, o relatório aparece na página — nota geral, aderência por competência, riscos e lacunas — com download do `.md` e do `.json`. Sem microfone, degrada para respostas digitadas.

### API de integração (`/api/v1`)

Rotas **sem estado** para consumo por outros backends (por exemplo, um sistema em Spring que é o dono dos cadastros): cada chamada envia os dados completos e recebe o resultado, sem sessão nem escrita em disco. Documentação interativa em `/docs` e contrato OpenAPI em `/openapi.json` (útil para gerar clientes automaticamente).

| Rota | Corpo | Retorno |
|---|---|---|
| `POST /api/v1/roteiro` | `{ "vaga": {...}, "candidato": {...} }` | `{ "perguntas": [...] }` |
| `POST /api/v1/transcricao` | multipart: `audio` (arquivo) e `modelo` opcional | `{ "texto": "...", "modelo": "small" }` |
| `POST /api/v1/analise` | `{ "vaga": {...}, "respostas": [...] }` | análise completa, mais `"metodo"` |
| `POST /api/v1/relatorio` | `{ "vaga", "candidato", "respostas", "analise" }` | `{ "relatorio_md": "...", "relatorio_json": {...} }` |

Os formatos de `vaga`, `candidato` e `respostas` são os dos arquivos de `dados/` e do roteiro gerado (modelos em `iauto/dominio/modelos.py`).

### Análise semântica com LLM (opcional)

Com `OPENROUTER_API_KEY` e `OPENROUTER_MODEL` configuradas (chave e slug de modelo de <https://openrouter.ai/models>), a análise de aderência passa a ser feita por um LLM, que entende sinônimos, contexto e profundidade das respostas. Os campos objetivos (contagem de palavras, termos identificados, presença de exemplo) continuam calculados deterministicamente, e a nota geral é sempre a média ponderada pelos pesos. Sem as variáveis — ou em qualquer falha do serviço — a análise cai automaticamente para a heurística local; o campo `metodo` indica o caminho usado.

Outras variáveis de ambiente: `VOZ_TTS` (voz do entrevistador, padrão `pt-BR-FranciscaNeural`), `MODELO_ASR`, `PORT`/`HOST` (deploy).

## Estrutura dos dados

`dados/vaga_exemplo.json`: título, empresa, descrição e lista de competências, cada uma com `nome`, `peso` e `palavras_chave`.

`dados/candidato_exemplo.json`: `nome`, `resumo` e lista de `experiencias` (frases do currículo, usadas para personalizar as perguntas).

## Limites e próximos passos

- Perguntas de acompanhamento dinâmicas (aprofundar com base na resposta anterior) pedem um LLM no laço da entrevista.
- Integração com a API oficial do WhatsApp para receber os áudios e devolver o resultado.
- Sessões da entrevista web vivem em memória (processo único); escala horizontal pede um armazenamento compartilhado.
- Fila de processamento (por exemplo, RabbitMQ) para transcrever entrevistas em escala.
