"""
pc_prueba_voz.py  -  CORRE EN EL PC
Prueba la voz de Doby con una conversion de audio de mejor calidad:
  1. Genera la frase con gTTS
  2. La convierte a 16 kHz con remuestreo de calidad (scipy)
  3. Le quita los graves que el parlante pequeno no puede reproducir
  4. La reproduce en el PC y luego en la ESP32, para comparar

Ejecutar desde la carpeta del proyecto con:  py pc_prueba_voz.py
"""

import os
import socket
import time
import wave
import winsound
from math import gcd

os.environ["SDL_AUDIODRIVER"] = "dummy"          # pygame sin usar los parlantes del PC
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import numpy as np
from scipy.signal import butter, resample_poly, sosfilt

import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc"))
from config import IP_ESP32   # la IP de la ESP32 se cambia en pc/config.py
PUERTO = 5000
TASA = 16000            # frecuencia que usa la ESP32
TASA_GTTS = 24000       # frecuencia original de gTTS
VOLUMEN = 0.35          # 0.0 a 1.0  -> no pasar de 0.5 (parlante de 1.5 W)
CORTE_GRAVES = 200      # Hz: por debajo de esto el parlante solo distorsiona
FRASE = "Hola amo, ¿qué vamos a hacer hoy?"


def generar_voz(texto):
    """Genera la voz con gTTS y la entrega a 16 kHz con buena calidad."""
    from gtts import gTTS
    import pygame

    gTTS(texto, lang="es", tld="com.mx").save("voz.mp3")

    # Decodificar el MP3 en su frecuencia original (sin que pygame la cambie)
    pygame.mixer.init(frequency=TASA_GTTS, size=-16, channels=1)
    tasa_real = pygame.mixer.get_init()[0]
    muestras = pygame.sndarray.array(pygame.mixer.Sound("voz.mp3")).astype(np.float32)
    pygame.mixer.quit()

    if muestras.ndim > 1:
        muestras = muestras.mean(axis=1)

    # Remuestreo de calidad a 16 kHz (con filtro antialiasing)
    g = gcd(TASA, tasa_real)
    return resample_poly(muestras, TASA // g, tasa_real // g)


def pulir(audio):
    """Quita graves, normaliza el volumen y suaviza inicio y final."""
    audio = audio.astype(np.float32)
    audio -= audio.mean()

    filtro = butter(2, CORTE_GRAVES, btype="highpass", fs=TASA, output="sos")
    audio = sosfilt(filtro, audio)

    pico = np.max(np.abs(audio))
    if pico > 0:
        audio = audio / pico * VOLUMEN * 32767

    n = int(0.01 * TASA)                  # 10 ms de rampa para evitar "clics"
    rampa = np.linspace(0, 1, n)
    audio[:n] *= rampa
    audio[-n:] *= rampa[::-1]
    return audio.astype(np.int16)


def guardar_wav(audio_16, ruta):
    with wave.open(ruta, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TASA)
        wav.writeframes(audio_16.astype("<i2").tobytes())


def leer_wav(ruta):
    with wave.open(ruta, "rb") as wav:
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")


def enviar(audio_16, nombre):
    silencio = np.zeros(int(0.3 * TASA), dtype=np.int16)
    datos = np.concatenate([audio_16, silencio]).astype("<i2").tobytes()
    duracion = len(datos) / 2 / TASA
    print("   Enviando {} a la ESP32 ({:.1f} s)...".format(nombre, duracion))
    with socket.create_connection((IP_ESP32, PUERTO), timeout=10) as conexion:
        conexion.sendall(datos)
    time.sleep(duracion + 0.5)


print("=" * 50)
print(" PRUEBA DE LA VOZ DE DOBY (version mejorada)")
print("=" * 50)

print("1. Generando la voz...")
voz = pulir(generar_voz(FRASE))
guardar_wav(voz, "voz_doby_16k.wav")

print("2. Escucha en los parlantes del PC...")
winsound.PlaySound("voz_doby_16k.wav", winsound.SND_FILENAME)
time.sleep(0.5)

print("3. Ahora escucha en el parlante de la ESP32...")
enviar(voz, "voz de Doby")

if os.path.exists("grabacion.wav"):
    print("4. Tu voz grabada, por el parlante de la ESP32...")
    enviar(pulir(leer_wav("grabacion.wav")), "tu grabacion")
else:
    print("4. (No hay grabacion.wav en esta carpeta, salto esa prueba)")

print("Prueba terminada.")
