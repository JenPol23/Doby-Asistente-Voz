# ============================================================
#  esp32_prueba_mic.py  -  CORRE EN LA ESP32 (desde Thonny)
#  Envia al PC, por WiFi, lo que capta el microfono INMP441.
# ============================================================

import network
import socket
import time
from machine import Pin, I2S

from secretos import RED, CLAVE   # datos del WiFi: secretos.py en la placa (plantilla esp32/secretos.ejemplo.py)
PUERTO = 5000

# ---------------- WiFi ----------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
try:
    wlan.config(pm=wlan.PM_NONE)   # sin ahorro de energia
except Exception:
    pass

if not wlan.isconnected():
    print("Conectando al WiFi...")
    wlan.connect(RED, CLAVE)
    for i in range(20):
        if wlan.isconnected():
            break
        time.sleep(1)

print("IP de la ESP32:", wlan.ifconfig()[0])

# ---------------- Microfono ----------------
mic = I2S(
    1,
    sck=Pin(4),
    ws=Pin(5),
    sd=Pin(6),
    mode=I2S.RX,
    bits=32,
    format=I2S.MONO,
    rate=16000,
    ibuf=16000,
)
buf = bytearray(4096)   # 1024 muestras = 64 ms de audio

# ---------------- Servidor ----------------
servidor = socket.socket()
servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
servidor.bind(("0.0.0.0", PUERTO))
servidor.listen(1)
print("Esperando al PC en el puerto", PUERTO, "...")

while True:
    cliente, direccion = servidor.accept()
    print("PC conectado:", direccion)
    try:
        while True:
            leidos = mic.readinto(buf)
            if leidos:
                cliente.write(memoryview(buf)[:leidos])
    except OSError:
        print("PC desconectado")
    cliente.close()
