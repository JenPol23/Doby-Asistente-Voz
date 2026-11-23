"""
prueba_escucha.py  -  CORRE EN EL PC
Prueba la deteccion de voz (pc/entrada_audio.py) y Whisper (pc/stt.py) con el
microfono de la ESP32 (esp32/main.py ya cargado en la placa):
  1. Carga Whisper medium (GPU o CPU)
  2. Calibra 2 s de ruido (todo apagado y en silencio)
  3. Escucha 3 frases y muestra texto, duracion, tiempo de Whisper y tiempo total
  4. Guarda la ultima frase en pruebas/ultima_frase.wav

Ejecutar desde la carpeta del proyecto con:  py pruebas/prueba_escucha.py
"""

import os
import sys
import time
import wave

import numpy as np

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, "..", "pc"))

import config
from stt import Stt                    # primero: importa torch antes que faster_whisper
from entrada_audio import EntradaAudio
from esp32_cliente import Esp32Cliente

FRASES = 3
ARCHIVO_WAV = os.path.join(CARPETA, "ultima_frase.wav")

print("=" * 50)
print(" PRUEBA DE ESCUCHA: deteccion de voz + Whisper")
print("=" * 50)

print("\n1. Cargando Whisper...")
inicio = time.perf_counter()
stt = Stt()
print("   ({:.1f} s)".format(time.perf_counter() - inicio))

print("\n2. ESP32:")
esp = Esp32Cliente()
esp.conectar()
entrada = EntradaAudio(esp)

print("\n3. Calibrando 2 s de ruido: NO hables y deja todo apagado...")
entrada.calibrar()

print("\n4. Di {} frases, una por una.".format(FRASES))
audio = None
for i in range(1, FRASES + 1):
    print("\n[Frase {}] Habla cuando quieras...".format(i))
    audio, seg_voz, t_ultima_voz = entrada.escuchar_frase()

    inicio = time.perf_counter()
    texto = stt.transcribir(audio)
    fin = time.perf_counter()

    print('   Whisper:        "{}"'.format(texto if texto else "(nada)"))
    print("   Duracion voz:   {:.2f} s  (audio enviado a Whisper: {:.2f} s)".format(
        seg_voz, len(audio) / config.TASA))
    print("   Tiempo Whisper: {:.2f} s".format(fin - inicio))
    print("   Total desde que dejaste de hablar: {:.2f} s".format(fin - t_ultima_voz))

with wave.open(ARCHIVO_WAV, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(config.TASA)
    wav.writeframes(np.clip(audio * 32768, -32768, 32767).astype("<i2").tobytes())
print("\nUltima frase guardada en", ARCHIVO_WAV)

esp.cerrar()
print("Prueba terminada.")
