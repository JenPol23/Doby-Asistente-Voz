"""
pc_prueba_mic.py  -  CORRE EN EL PC
Recibe 5 segundos del microfono de la ESP32 por WiFi,
los guarda en grabacion.wav y los reproduce.

Ejecutar con:  py pc_prueba_mic.py
"""

import socket
import time
import wave
import winsound

import numpy as np

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pc"))
from config import IP_ESP32   # la IP de la ESP32 se cambia en pc/config.py
PUERTO = 5000
SEGUNDOS = 5
TASA = 16000
ARCHIVO = "grabacion.wav"

print("Conectando a la ESP32 en {}:{}...".format(IP_ESP32, PUERTO))
conexion = socket.create_connection((IP_ESP32, PUERTO), timeout=5)
print("Conectado. HABLA cerca del microfono durante {} segundos...".format(SEGUNDOS))

total_bytes = TASA * 4 * SEGUNDOS      # 4 bytes por muestra (32 bits)
datos = bytearray()
inicio = time.time()

while len(datos) < total_bytes:
    trozo = conexion.recv(8192)
    if not trozo:
        raise RuntimeError("La ESP32 cerro la conexion")
    datos += trozo

conexion.close()
duracion = time.time() - inicio

print()
print("Tiempo de recepcion: {:.1f} s (lo ideal es cerca de {} s)".format(duracion, SEGUNDOS))

# ---------------- Convertir el audio ----------------
muestras = np.frombuffer(bytes(datos[:total_bytes]), dtype="<i4")
audio = (muestras >> 16).astype(np.float32)   # los 16 bits mas importantes
audio -= audio.mean()                          # quita el desnivel de continua

promedio = float(np.mean(np.abs(audio)))
pico = float(np.max(np.abs(audio)))
print("Nivel promedio: {:.0f}   Pico: {:.0f}".format(promedio, pico))

# Subir el volumen para escucharlo bien (sin saturar)
ganancia = min(20.0, 30000.0 / pico) if pico > 0 else 1.0
print("Ganancia aplicada para escuchar: x{:.1f}".format(ganancia))
audio_16 = np.clip(audio * ganancia, -32768, 32767).astype(np.int16)

with wave.open(ARCHIVO, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(TASA)
    wav.writeframes(audio_16.tobytes())

print("Guardado en", ARCHIVO)
print("Reproduciendo...")
winsound.PlaySound(ARCHIVO, winsound.SND_FILENAME)
print("Listo.")
