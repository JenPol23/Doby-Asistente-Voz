"""
prueba_protocolo.py  -  CORRE EN EL PC
Prueba el protocolo de Doby con la ESP32 (esp32/main.py ya cargado en la placa):
  1. PING
  2. Reles 1 a 3: encender y apagar (deben sonar los clics)
  3. 3 s de microfono guardados en pruebas/prueba_protocolo.wav
  4. Un pitido por el parlante de la ESP32

Ejecutar desde la carpeta del proyecto con:  py pruebas/prueba_protocolo.py
"""

import os
import sys
import time
import wave

import numpy as np

CARPETA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CARPETA, "..", "pc"))

import config
from esp32_cliente import Esp32Cliente

SEGUNDOS_MIC = 3
ARCHIVO_WAV = os.path.join(CARPETA, "prueba_protocolo.wav")
NOMBRES = {numero: nombre for nombre, numero in config.APARATOS.items()}

print("=" * 50)
print(" PRUEBA DEL PROTOCOLO PC <-> ESP32")
print("=" * 50)

esp = Esp32Cliente()
esp.conectar()

# ---------------- 0. Estado inicial ----------------
print("\n0. TODOS 0 (todo apagado al arrancar):", "OK" if esp.todos_apagados() else "ERROR")

# ---------------- 1. PING ----------------
print("\n1. PING")
for i in range(3):
    inicio = time.perf_counter()
    respuesta = esp.ping()
    ms = (time.perf_counter() - inicio) * 1000
    print("   PING {}: {} ({:.0f} ms)".format(i + 1, "PONG" if respuesta else "SIN RESPUESTA", ms))

# ---------------- 2. Reles ----------------
print("\n2. RELES (escucha los clics)")
for k in (1, 2, 3):
    nombre = NOMBRES.get(k, "rele {}".format(k))
    print("   Encendiendo rele {} ({}):".format(k, nombre), "OK" if esp.rele(k, 1) else "ERR")
    time.sleep(1.5)
    print("   Apagando rele {} ({}):".format(k, nombre), "OK" if esp.rele(k, 0) else "ERR")
    time.sleep(0.5)
print("   Orden invalida RELE 9 1 (debe dar ERR):", "OK" if esp.rele(9, 1) else "ERR")

# ---------------- 3. Microfono ----------------
print("\n3. MICROFONO: habla cerca del microfono durante {} s...".format(SEGUNDOS_MIC))
bloques = int(SEGUNDOS_MIC * config.TASA / 1024)
inicio = time.perf_counter()
crudo = np.concatenate([esp.leer_mic() for _ in range(bloques)])
duracion = time.perf_counter() - inicio

audio = (crudo >> 16).astype(np.float32)       # los 16 bits mas importantes
audio -= audio.mean()                          # quita el desnivel de continua
print("   {} bloques MIC en {:.2f} s (audio real: {:.2f} s)".format(
    bloques, duracion, len(crudo) / config.TASA))
print("   Nivel promedio: {:.0f}   Pico: {:.0f}".format(
    float(np.mean(np.abs(audio))), float(np.max(np.abs(audio)))))

with wave.open(ARCHIVO_WAV, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(config.TASA)
    wav.writeframes(np.clip(audio, -32768, 32767).astype("<i2").tobytes())
print("   Guardado en", ARCHIVO_WAV)

# ---------------- 4. Pitido ----------------
print("\n4. PITIDO de 880 Hz por el parlante de la ESP32 (0.5 s)")
t = np.arange(int(0.5 * config.TASA)) / config.TASA
tono = np.sin(2 * np.pi * 880 * t) * config.VOLUMEN * 32767
n = int(0.01 * config.TASA)                    # 10 ms de rampa para evitar clics
rampa = np.linspace(0, 1, n)
tono[:n] *= rampa
tono[-n:] *= rampa[::-1]

inicio = time.perf_counter()
ok = esp.hablar(tono.astype(np.int16))
print("   HABLAR:", "OK" if ok else "ERROR", "({:.2f} s hasta el OK)".format(time.perf_counter() - inicio))

esp.cerrar()
print("\nPrueba terminada.")
