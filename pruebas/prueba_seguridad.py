"""
prueba_seguridad.py  -  CORRE EN EL PC, SIN ESP32
Apagados de seguridad del cautin y la plancha en el lado del PC (el del firmware: pruebas/prueba_firmware.py;
la logica del apagado automatico con reloj virtual: seccion 7 de pruebas/prueba_ordenes.py).
  1. entrada_audio.escuchar_frase(): sin al_esperar, la misma frase que antes; con al_esperar, se llama en
     cada bloque sin voz y la frase se detecta igual.
  2. Modo voz completo (modo_voz() real, Whisper real, ESP32 falsa de prueba_verificacion.py) con
     APAGADO_AUTOMATICO = 0.1 min: "Hola Doby" + "Prende el cautin." y, sin hablar, a los 6 s
     RELE 2 0 + "Por seguridad, apague el cautin.".
  3. Al cerrar Doby (apagar_calientes_al_salir): RELE k 0 de config.CALIENTES por una conexion nueva a un
     servidor TCP local que hace de ESP32; sin ESP32, no se queda esperando y avisa.

Uso:  py pruebas/prueba_seguridad.py      (codigo de salida 1 si algun caso falla)
"""

import contextlib
import io
import os
import socket
import sys
import threading
import time

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))
sys.path.insert(0, os.path.join(RAIZ, "pruebas"))

import config                  # noqa: E402
import doby                    # noqa: E402
import entrada_audio           # noqa: E402
import esp32_cliente           # noqa: E402
import prueba_verificacion as pv   # noqa: E402  (ESP32 falsa con microfono y sesion() con modo_voz real)

resultados = []
AUDIO_CAUTIN = os.path.join(RAIZ, "voz_comparacion_f5", "_prueba_aparatos", "gtts", "n01.wav")   # "Prende el cautín."


def informe(nombre, ok, detalle=""):
    resultados.append((nombre, ok))
    print("  {}  {}{}".format("PASA " if ok else "FALLA", nombre, "" if ok or not detalle else "\n     " + detalle))


# ---------------- 1. entrada_audio con al_esperar ----------------
class MicFalso:
    """6 s: ruido de fondo y 1 s de tono fuerte (la 'voz') a los 3 s."""

    def __init__(self):
        azar = np.random.default_rng(1)
        senal = azar.normal(0, 150, 16000 * 6)
        senal[16000 * 3:16000 * 4] += 6000 * np.sin(np.arange(16000) * 2 * np.pi * 300 / 16000)
        self.senal, self.pos = np.round(senal).astype(np.int32), 0

    def pedir_mic(self):
        pass

    def recibir_mic(self):
        b = self.senal[self.pos:self.pos + 1024]
        self.pos += 1024
        return b << 16


def escuchar(al_esperar=None):
    e = entrada_audio.EntradaAudio(MicFalso())
    e.umbral = 1500
    with contextlib.redirect_stdout(io.StringIO()):
        return e.escuchar_frase() if al_esperar is None else e.escuchar_frase(al_esperar(e))


def prueba_entrada():
    a0, s0, _ = escuchar()
    llamadas = []

    def fabrica(e):
        def al_esperar():
            llamadas.append(e.esp.pos)
            if len(llamadas) == 10:            # una vez usa el socket, como el apagado automatico
                e.vaciar()
                e.descartar(0.3)
                return True
            return False
        return al_esperar

    a1, s1, _ = escuchar(fabrica)
    informe("1. al_esperar se llama en cada bloque sin voz ({} veces) y la frase se detecta igual ({:.2f} s y {:.2f} s)"
            .format(len(llamadas), s0, s1), len(llamadas) > 10 and abs(s1 - s0) < 0.07 and len(a1) > 0)


# ---------------- 2. Modo voz con Whisper ----------------
def prueba_modo_voz():
    config.VERIFICAR_HABLANTE = config.VERIFICAR_ORDENES = config.VOZ_CLONADA = False
    config.APAGADO_AUTOMATICO = 0.1
    try:
        eventos, _, _ = pv.sesion([pv.toma("jenpol", "A", 1), pv.leer_wav(AUDIO_CAUTIN), np.zeros(16000 * 10)])
    finally:
        config.APAGADO_AUTOMATICO = 10
    secuencia = [e for e in eventos if e[0] in ("rele", "dice") and e[1] not in ("saludo_1", "saludo_2")]
    esperado = [["rele", 2, 1], ["dice", "encendi_cautin"], ["rele", 2, 0], ["dice", "auto_apagado_cautin"]]
    informe("2. Modo voz: 'Hola Doby' + 'Prende el cautín.' y, sin hablar, a los 6 s RELE 2 0 + "
            "'Por seguridad, apagué el cautín.'", secuencia == esperado, "eventos {}".format(eventos))


# ---------------- 3. Al cerrar Doby ----------------
def servidor_falso():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    recibido = []

    def atender():
        c, _ = s.accept()
        for linea in c.makefile("rb"):
            recibido.append(linea.decode().strip())
            c.sendall(b"OK\n")
        c.close()
    threading.Thread(target=atender, daemon=True).start()
    return s.getsockname()[1], recibido


def puerto_libre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    puerto = s.getsockname()[1]
    s.close()
    return puerto


def prueba_salida():
    esperado = ["RELE {} 0".format(config.APARATOS[a]) for a in config.CALIENTES]
    puerto, recibido = servidor_falso()
    with contextlib.redirect_stdout(io.StringIO()):
        ok = doby.apagar_calientes_al_salir(esp32_cliente.Esp32Cliente(ip="127.0.0.1", puerto=puerto))
    time.sleep(0.3)
    informe("3a. Al cerrar, con ESP32: manda {} y lo confirma".format(" y ".join(esperado)),
            ok and recibido == esperado, "ok {} | recibido {}".format(ok, recibido))

    t = time.perf_counter()
    with contextlib.redirect_stdout(io.StringIO()) as salida:
        ok = doby.apagar_calientes_al_salir(esp32_cliente.Esp32Cliente(ip="127.0.0.1", puerto=puerto_libre()))
    seg = time.perf_counter() - t
    informe("3b. Al cerrar, sin ESP32: se rinde en {:.1f} s (3 intentos) y avisa en grande".format(seg),
            not ok and seg < 20 and "NO SE PUDO CONFIRMAR" in salida.getvalue(), salida.getvalue()[-200:])

    with contextlib.redirect_stdout(io.StringIO()) as salida:
        ok = esp32_cliente.Esp32Cliente(ip="127.0.0.1", puerto=puerto_libre()).conectar(intentos=2)
    informe("3c. Esp32Cliente.conectar(intentos=2): reintenta una vez y devuelve False",
            ok is False and salida.getvalue().count("Reintento") == 1)


def main():
    prueba_entrada()
    prueba_modo_voz()
    prueba_salida()
    n = sum(ok for _, ok in resultados)
    print("\n{} de {} casos pasan".format(n, len(resultados)))
    return n == len(resultados)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
