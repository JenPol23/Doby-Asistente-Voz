"""
prueba_voz_doby.py  -  CORRE EN EL PC
Pregenera todas las frases de Doby (pc/tts.py) y las reproduce, una por una,
por el parlante de la ESP32.

Ejecutar desde la carpeta del proyecto con:  py pruebas/prueba_voz_doby.py
"""

import os
import sys
import time

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, "..", "pc"))

import tts
from esp32_cliente import Esp32Cliente

print("=" * 60)
print(" PRUEBA DE LA VOZ DE DOBY ({} frases)".format(len(tts.FRASES)))
print("=" * 60)

print("\n1. Pregenerando frases en voz_cache/...")
tts.pregenerar()

print("\n2. Reproduciendo por el parlante de la ESP32...")
esp = Esp32Cliente()
esp.conectar()

fallas = 0
for i, (clave, texto) in enumerate(tts.FRASES.items(), 1):
    inicio = time.perf_counter()
    ok = esp.hablar(tts.obtener(clave))
    if not ok:
        fallas += 1
    print("  {:2d}. {:28} {:5} ({:.1f} s)  {}".format(
        i, clave, "OK" if ok else "ERROR", time.perf_counter() - inicio, texto))
    time.sleep(0.3)

esp.cerrar()
print("\nPrueba terminada: {} de {} frases con OK.".format(len(tts.FRASES) - fallas, len(tts.FRASES)))
