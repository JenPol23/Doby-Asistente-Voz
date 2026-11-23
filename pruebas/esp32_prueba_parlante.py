# ============================================================
#  esp32_prueba_parlante.py  -  CORRE EN LA ESP32 (desde Thonny)
#  Recibe audio del PC por WiFi y lo reproduce por el MAX98357.
#  Formato esperado: PCM 16 bits, mono, 16 kHz.
# ============================================================

import network
import socket
import time
from machine import Pin, I2S

from secretos import RED, CLAVE   # datos del WiFi: secretos.py en la placa (plantilla esp32/secretos.ejemplo.py)
PUERTO = 5000


# ---------------- WiFi ----------------
def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)

    # Reinicia el WiFi para limpiar cualquier intento anterior
    wlan.active(False)
    time.sleep(0.5)
    wlan.active(True)
    try:
        wlan.config(pm=wlan.PM_NONE)   # sin ahorro de energia
    except Exception:
        pass

    intento = 0
    while not wlan.isconnected():
        intento += 1
        print("Conectando al WiFi (intento {})...".format(intento))
        try:
            wlan.connect(RED, CLAVE)
        except OSError as e:
            print("  error:", e)

        for _ in range(15):
            if wlan.isconnected():
                break
            time.sleep(1)

        if not wlan.isconnected():
            print("  No se pudo. El punto de acceso esta encendido y en 2.4 GHz?")
            try:
                wlan.disconnect()
            except Exception:
                pass
            time.sleep(3)

    print("WiFi conectado. IP de la ESP32:", wlan.ifconfig()[0])
    return wlan


wlan = conectar_wifi()

# ---------------- Parlante ----------------
parlante = I2S(
    0,
    sck=Pin(15),
    ws=Pin(16),
    sd=Pin(7),
    mode=I2S.TX,
    bits=16,
    format=I2S.MONO,
    rate=16000,
    ibuf=20000,
)

buf = bytearray(4096)
mv = memoryview(buf)


def leer_bloque(cliente):
    """Llena el buffer completo para no cortar muestras por la mitad."""
    total = 0
    while total < len(buf):
        n = cliente.readinto(mv[total:])
        if not n:
            break
        total += n
    return total


# ---------------- Servidor ----------------
servidor = socket.socket()
servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
servidor.bind(("0.0.0.0", PUERTO))
servidor.listen(1)
print("Esperando audio del PC en el puerto", PUERTO, "...")

while True:
    cliente, direccion = servidor.accept()
    print("PC conectado:", direccion)
    recibidos = 0
    try:
        while True:
            n = leer_bloque(cliente)
            if n == 0:
                break
            n -= n % 2                    # siempre muestras completas
            parlante.write(mv[:n])
            recibidos += n
    except OSError:
        pass
    cliente.close()
    print("Reproducidos {:.1f} s de audio".format(recibidos / 32000))
