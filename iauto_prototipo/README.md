# iAuto: protótipo de entrevista automatizada por áudio (PT-BR)

Protótipo simples, em Python puro, do módulo de Entrevista Automatizada (iAuto). O fluxo cobre as etapas previstas no projeto:

1. **Roteiro personalizado** (`roteiro.py`): correlaciona o perfil do candidato com as competências da vaga. Quando encontra uma experiência do currículo ligada à competência, a pergunta cita essa experiência; caso contrário, usa uma pergunta comportamental padrão.
2. **Entrevista por áudio em português** (`audio_io.py`): a pergunta é exibida e falada (TTS), um cronômetro marca o tempo na tela, o candidato pressiona Enter quando termina antes do prazo, e o estouro do tempo encerra a resposta e passa para a próxima pergunta. Sem avatar: o candidato apenas ouve, lê e responde.
3. **Transcrição ASR** (`transcricao.py`): usa o Whisper (arquitetura Transformer com mecanismo de atenção) via `faster-whisper`, executado localmente na CPU, com `language="pt"` e filtro de atividade de voz.
4. **Normalização e trechos relevantes** (`analise.py`): o texto é normalizado (minúsculas, sem acentos) e as frases que citam termos da competência são extraídas como trechos relevantes.
5. **Aderência por competência e relatório** (`relatorio.py`): nota de 0 a 100 por competência, nota geral ponderada pelos pesos da vaga e relatório por candidato com destaques, riscos e lacunas, em Markdown e em JSON.

## Instalação

Requer Python 3.10 ou superior.

```bash
pip install -r requirements.txt
```

Observações por sistema:

- Linux: `sudo apt install libportaudio2 espeak-ng` (áudio ao vivo e voz offline).
- O modo simulado não exige nenhuma dependência, roda com a biblioteca padrão.
- Na primeira transcrição, o modelo ASR é baixado automaticamente (o `small` tem cerca de 460 MB).

## Modos de execução

```bash
# 1) Entrevista ao vivo por voz (microfone e alto-falante)
python main.py --modo audio

# 2) Fluxo assíncrono, estilo WhatsApp: transcreve áudios já enviados
python main.py --modo lote --audios pasta_com_audios/

# 3) Teste do fluxo com respostas digitadas (sem áudio)
python main.py --modo simulado

# 4) Entrevista no navegador (interface web)
python servidor.py --porta 8123
# depois abra http://127.0.0.1:8123
```

### Interface web

O `servidor.py` sobe uma API (FastAPI) que reaproveita os mesmos módulos do CLI e serve a interface de `web/index.html`: a pergunta é exibida e falada pela voz do navegador, um cronômetro em anel marca o tempo, a resposta é gravada pelo microfone (com waveform ao vivo) e enviada para transcrição no servidor. Ao final, o relatório aparece na própria página — nota geral, aderência por competência, riscos e lacunas, transcrição completa — com download do `.md` e do `.json`. Sem microfone, a interface degrada para respostas digitadas. Com `--modelo auto` (padrão), o servidor usa o Whisper `small` se ele já estiver no cache local e `tiny` caso contrário.

### API de integração (`/api/v1`)

Além do fluxo de sessão da interface web, o servidor expõe rotas **sem estado** para integração com outros backends (por exemplo, um sistema em Spring que é o dono dos cadastros): cada chamada envia os dados completos e recebe o resultado, sem sessão nem escrita em disco. Documentação interativa em `/docs` e contrato OpenAPI em `/openapi.json` (útil para gerar clientes automaticamente).

| Rota | Corpo | Retorno |
|---|---|---|
| `POST /api/v1/roteiro` | `{ "vaga": {...}, "candidato": {...} }` | `{ "perguntas": [...] }` |
| `POST /api/v1/transcricao` | multipart: `audio` (arquivo) e `modelo` opcional (`auto`/`tiny`/`base`/`small`/`medium`) | `{ "texto": "...", "modelo": "small" }` |
| `POST /api/v1/analise` | `{ "vaga": {...}, "respostas": [...] }` | mesmo formato da análise do relatório, mais `"metodo"` |
| `POST /api/v1/relatorio` | `{ "vaga", "candidato", "respostas", "analise" }` | `{ "relatorio_md": "...", "relatorio_json": {...} }` |

Os formatos de `vaga`, `candidato` e `respostas` são os mesmos dos arquivos de `dados/` e do roteiro gerado.

### Análise semântica com LLM (opcional)

Com as variáveis de ambiente `OPENROUTER_API_KEY` e `OPENROUTER_MODEL` configuradas (chave e slug de modelo de <https://openrouter.ai/models>, por exemplo `anthropic/claude-sonnet-4.5`), a análise de aderência — tanto em `POST /api/v1/analise` quanto no fim da entrevista web — passa a ser feita por um LLM, que entende sinônimos, contexto e profundidade real das respostas. Os campos objetivos (contagem de palavras, termos identificados, presença de exemplo) continuam calculados deterministicamente em Python, e a nota geral é sempre a média ponderada pelos pesos. Sem as variáveis — ou em qualquer falha do serviço — a análise cai automaticamente para a heurística local, e o campo `metodo` da resposta indica qual caminho foi usado (`llm` ou `heuristico`).

Parâmetros úteis: `--vaga` e `--candidato` apontam para outros arquivos JSON, `--modelo` troca o tamanho do ASR (`tiny`, `base`, `small`, `medium`) e `--tempo` fixa um limite único de resposta em segundos no modo audio.

A saída de cada execução fica em `saida/<data>_<candidato>/`, com os WAV gravados (modo audio), o `relatorio.md` e o `relatorio.json`. A pasta `saida_exemplo/` traz um relatório já gerado, para conhecer o formato sem rodar nada.

## Relação com os dois produtos

- **Modo lote** corresponde ao produto por WhatsApp: o candidato envia mensagens de voz (o formato `.ogg`/`.opus` do WhatsApp é aceito) e o sistema transcreve e analisa tudo de forma assíncrona.
- **Modo audio** corresponde ao produto de entrevista ao vivo: pergunta falada, cronômetro visível, encerramento por tempo ou pelo próprio candidato.

Como ASR e TTS rodam localmente, o custo de IA por entrevista é praticamente zero de API, o que ajuda a fechar dentro da meta de custo discutida para o produto por WhatsApp.

## Estrutura dos dados

`dados/vaga_exemplo.json`: título, empresa, descrição e lista de competências, cada uma com `nome`, `peso` e `palavras_chave` (termos usados na análise de aderência).

`dados/candidato_exemplo.json`: `nome`, `resumo` e lista de `experiencias` (frases do currículo, usadas para personalizar as perguntas).

## Limites e próximos passos

- A análise de aderência é heurística (termos, profundidade e presença de exemplo). O próximo passo é uma camada semântica com embeddings ou com um LLM, mantendo o relatório no mesmo formato.
- Perguntas de acompanhamento dinâmicas (aprofundar com base na resposta anterior) pedem um LLM no laço da entrevista.
- Integração com a API oficial do WhatsApp para receber os áudios e devolver o resultado.
- Gravação de vídeo do rosto do candidato durante a resposta, no produto de chamada ao vivo.
- Fila de processamento (por exemplo, RabbitMQ) para transcrever entrevistas em escala.
