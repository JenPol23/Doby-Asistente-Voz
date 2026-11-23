"""
reproducir_en_parlante.py  -  CORRE EN EL PC (con la ESP32, sin arrancar Doby)
Envia audios al parlante de la ESP32 con HABLAR, con el MISMO procesado de las voces de Doby
(pc/tts.py): a 16 kHz con resample_poly, pasa-altos 200 Hz, pico a config.VOLUMEN, rampas de
10 ms y 0.3 s de silencio. Sirve para comparar voces candidatas en el parlante real.

Uso:
  py entrenamiento/reproducir_en_parlante.py voz_comparacion2/lina/saludo_1_t065_p085_s100_r50_v1.wav
  py entrenamiento/reproducir_en_parlante.py "voz_comparacion2/lina/saludo_1_*.wav"     (una por una)
  py entrenamiento/reproducir_en_parlante.py --tal-cual voz_cache_clonada/lina/saludo_1_99204169.wav
  --tal-cual: el archivo YA esta procesado para el parlante (16 kHz int16 de voz_cache/ o
              voz_cache_clonada/): se envia sin volver a procesarlo.
En cada audio: [Enter] reproducir, [s] saltar, [q] salir; despues: [Enter] siguiente, [r] repetir.
"""

import argparse
import glob
import os
import sys
import wave
from math import gcd

import numpy as np
from scipy.signal import resample_poly

from grabar_inmp441 import RAIZ, conectar_con_ping       # pone pc/ en sys.path
import config
import tts
from esp32_cliente import Esp32Cliente


def preparar_para_parlante(ruta):
    """Audio cualquiera (WAV, MP3, M4A...) -> int16 a 16 kHz con el procesado de tts.py."""
    import av
    from faster_whisper import decode_audio
    with av.open(ruta) as contenedor:
        sr = contenedor.streams.audio[0].rate
    x = decode_audio(ruta, sampling_rate=sr).astype(np.float64)          # mono, frecuencia nativa
    if sr != config.TASA:
        g = gcd(config.TASA, sr)
        x = resample_poly(x, config.TASA // g, sr // g)                   # igual que tts._generar_voz
    return tts._pulir(x)


def leer_tal_cual(ruta):
    with wave.open(ruta) as w:
        if w.getframerate() != config.TASA or w.getnchannels() != 1 or w.getsampwidth() != 2:
            sys.exit("{}: --tal-cual necesita WAV mono 16 kHz int16 (usa la opcion sin --tal-cual).".format(ruta))
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")


def main():
    parser = argparse.ArgumentParser(description="Reproduce audios en el parlante de la ESP32 (sin Doby).")
    parser.add_argument("audios", nargs="+", help="archivos o patrones (ej. \"voz_comparacion2/lina/*.wav\")")
    parser.add_argument("--tal-cual", action="store_true", help="enviar sin procesar (ya estan listos a 16 kHz)")
    args = parser.parse_args()

    rutas = []
    for patron in args.audios:
        encontrados = sorted(glob.glob(patron)) or ([patron] if os.path.exists(patron) else [])
        if not encontrados:
            print("AVISO: no hay archivos para '{}'".format(patron))
        rutas += encontrados
    if not rutas:
        sys.exit("No hay nada que reproducir.")

    esp = Esp32Cliente()
    if not conectar_con_ping(esp):
        sys.exit("La ESP32 no responde en {}:{} (enciendela y cierra Doby u otro script conectado).".format(
            esp.ip, esp.puerto))
    print("ESP32 lista. Volumen {:.2f} (config.VOLUMEN). {} audio(s).".format(config.VOLUMEN, len(rutas)))
    try:
        i = 0
        while i < len(rutas):
            ruta = rutas[i]
            nombre = os.path.relpath(ruta, RAIZ) if os.path.isabs(ruta) else ruta
            r = input("\n[{}/{}] {}  [Enter] reproducir, [s] saltar, [q] salir: ".format(
                i + 1, len(rutas), nombre)).strip().lower()
            if r == "q":
                break
            if r == "s":
                i += 1
                continue
            pcm = leer_tal_cual(ruta) if args.tal_cual else preparar_para_parlante(ruta)
            while True:
                print("  Reproduciendo {:.1f} s...".format(len(pcm) / config.TASA))
                if not esp.hablar(pcm):
                    print("  AVISO: la ESP32 no confirmo el audio.")
                r = input("  [Enter] siguiente, [r] repetir, [q] salir: ").strip().lower()
                if r != "r":
                    break
            if r == "q":
                break
            i += 1
    except KeyboardInterrupt:
        print()
    finally:
        esp.cerrar()


if __name__ == "__main__":
    main()
