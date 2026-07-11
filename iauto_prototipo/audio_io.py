"""Entrada e saída de áudio: voz do entrevistador (TTS) e gravação das respostas.

O fluxo de gravação segue o comportamento definido para o produto: a pergunta
é exibida e falada, um cronômetro marca o tempo, o candidato encerra com Enter
quando termina antes do prazo, e o estouro do tempo encerra a resposta e passa
para a próxima pergunta.
"""

import os
import sys
import time


def falar(texto):
    """Fala o texto em português. Sem TTS disponível, a pergunta fica só na tela."""
    # Primeira opção: pyttsx3, que funciona offline (no Linux exige espeak-ng).
    try:
        import pyttsx3
        motor = pyttsx3.init()
        for voz in motor.getProperty("voices"):
            identificacao = f"{voz.id} {getattr(voz, 'name', '')}".lower()
            if "pt" in identificacao or "brazil" in identificacao or "portug" in identificacao:
                motor.setProperty("voice", voz.id)
                break
        motor.setProperty("rate", 170)
        motor.say(texto)
        motor.runAndWait()
        return True
    except Exception:
        pass

    # Segunda opção: gTTS, que usa a internet e tem voz PT-BR de boa qualidade.
    try:
        import subprocess
        import tempfile

        from gtts import gTTS

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as arquivo:
            caminho = arquivo.name
        gTTS(texto, lang="pt", tld="com.br").save(caminho)
        tocadores = [
            ["mpv", "--really-quiet", caminho],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", caminho],
            ["mpg123", "-q", caminho],
        ]
        for comando in tocadores:
            try:
                subprocess.run(comando, check=True)
                os.unlink(caminho)
                return True
            except Exception:
                continue
        os.unlink(caminho)
    except Exception:
        pass
    return False


if os.name == "nt":
    import msvcrt

    def _enter_pressionado():
        while msvcrt.kbhit():
            tecla = msvcrt.getwch()
            if tecla in ("\r", "\n"):
                return True
        return False
else:
    import select

    def _enter_pressionado():
        prontos, _, _ = select.select([sys.stdin], [], [], 0)
        if prontos:
            sys.stdin.readline()
            return True
        return False


def gravar_resposta(caminho_wav, tempo_max=90, taxa=16000):
    """Grava a resposta até o limite de tempo. Enter encerra antes do prazo."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    print(
        f"[GRAVANDO] Responda em voz alta. Tempo máximo: {tempo_max}s. "
        "Pressione Enter quando terminar."
    )
    blocos = []
    inicio = time.time()
    encerrado_por = "tempo"
    with sd.InputStream(samplerate=taxa, channels=1, dtype="int16") as fluxo:
        while True:
            restante = tempo_max - (time.time() - inicio)
            if restante <= 0:
                break
            bloco, _ = fluxo.read(int(taxa * 0.25))
            blocos.append(bloco.copy())
            print(f"\r  tempo restante: {max(0, int(restante)):3d}s ", end="", flush=True)
            if _enter_pressionado():
                encerrado_por = "candidato"
                break
    print()
    if encerrado_por == "tempo":
        print("[TEMPO ESGOTADO] Encerrando esta resposta e seguindo para a próxima pergunta.")
    else:
        print("[OK] Resposta encerrada pelo candidato.")

    audio = np.concatenate(blocos) if blocos else np.zeros((1, 1), dtype="int16")
    sf.write(caminho_wav, audio, taxa)
    return caminho_wav
