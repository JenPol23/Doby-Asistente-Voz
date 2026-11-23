"""
diagnostico_mic.py  -  CORRE EN EL PC CON LA ESP32 REAL (cerrar Doby antes: la ESP32 atiende un solo PC)
Busca la causa de "Se perdio la conexion con el microfono (timed out)" justo despues de que Doby habla.
Repite lo mismo que hace Doby (HABLAR una frase, descartar 0.3 s, escuchar con 2 MIC en vuelo) pero con
un tiempo de espera de 15 s en vez de 2 s, y mide cuanto tarda en llegar CADA bloque de 64 ms:
  - si algun bloque tarda mas de 2 s pero LLEGA: es un atasco de la red (TCP reenvia): basta con esperar
    mas en el PC (TIMEOUT_MIC en pc/esp32_cliente.py);
  - si alguno no llega ni en 15 s: la respuesta se perdio en la ESP32 (habria que revisar esp32/main.py);
  - las rondas de control (sin HABLAR) dicen si pasa igual sin que Doby hable.

Uso:  py pruebas/diagnostico_mic.py [--rondas 15] [--seg 5]
Salida: logs/diagnostico_mic_<fecha_hora>.csv (una fila por bloque) y un resumen en consola.
Dependencias (por importacion, sin modificarlas): pc/esp32_cliente.py (Esp32Cliente; aqui se sube
TIMEOUT_MIC solo en este proceso), pc/voz_clonada.py (audio de la frase).
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))

import esp32_cliente               # noqa: E402
import voz_clonada                 # noqa: E402

ESPERA_DIAGNOSTICO = 15.0          # s; Doby usa esp32_cliente.TIMEOUT_MIC = 2.0
LIMITE_DOBY = esp32_cliente.TIMEOUT_MIC
EN_VUELO = 2


def escuchar(esp, segundos):
    """Bloques MIC con 2 en vuelo, como entrada_audio.py. Devuelve [(s desde el pedido anterior, ok)]."""
    tiempos, pendientes = [], 0
    for _ in range(int(segundos / 0.064)):
        while pendientes < EN_VUELO:
            esp.pedir_mic()
            pendientes += 1
        t = time.perf_counter()
        try:
            esp.recibir_mic()
            pendientes -= 1
            tiempos.append((time.perf_counter() - t, True))
        except (OSError, ConnectionError):
            tiempos.append((time.perf_counter() - t, False))
            esp.conectar()
            pendientes = 0
    try:
        while pendientes:
            esp.recibir_mic()
            pendientes -= 1
    except (OSError, ConnectionError):
        esp.conectar()
    return tiempos


def main():
    parser = argparse.ArgumentParser(description="Diagnostico del microfono despues de HABLAR")
    parser.add_argument("--rondas", type=int, default=15, help="rondas con HABLAR (y otras tantas de control)")
    parser.add_argument("--seg", type=float, default=5.0, help="segundos de microfono por ronda")
    args = parser.parse_args()

    esp32_cliente.TIMEOUT_MIC = ESPERA_DIAGNOSTICO          # solo en este proceso
    frase = voz_clonada.obtener("jenpol", "saludo_1")
    esp = esp32_cliente.Esp32Cliente()
    esp.conectar()
    os.makedirs(os.path.join(RAIZ, "logs"), exist_ok=True)
    ruta = os.path.join(RAIZ, "logs", "diagnostico_mic_{}.csv".format(datetime.now().strftime("%Y-%m-%d_%H%M")))
    filas, resumen = [], []
    plan = [("hablar", r) for r in range(args.rondas)] + [("control", r) for r in range(args.rondas)]
    for tipo, r in plan:
        if tipo == "hablar":
            if not esp.hablar(frase):
                print("  AVISO: HABLAR sin OK")
            escuchar(esp, 0.3)                              # el descarte de Doby
        else:
            time.sleep(3.0)                                 # mismo ritmo, sin parlante
        tiempos = escuchar(esp, args.seg)
        for i, (s, ok) in enumerate(tiempos):
            filas.append({"tipo": tipo, "ronda": r, "bloque": i, "seg": round(s, 4), "llego": ok})
        mx = max(s for s, _ in tiempos)
        lentos = sum(s > LIMITE_DOBY for s, _ in tiempos)
        perdidos = sum(not ok for _, ok in tiempos)
        resumen.append((tipo, mx, lentos, perdidos))
        print("  {:7} ronda {:2}: bloque mas lento {:5.2f} s | > {:.0f} s (Doby se habria reconectado): {} | "
              "no llegaron en {:.0f} s: {}".format(tipo, r + 1, mx, LIMITE_DOBY, lentos, ESPERA_DIAGNOSTICO, perdidos))
    esp.cerrar()
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print("\nResumen ({}):".format(os.path.relpath(ruta, RAIZ)))
    for tipo in ("hablar", "control"):
        x = [t for t in resumen if t[0] == tipo]
        print("  {:7}: rondas con un bloque > {:.0f} s: {} de {} | bloques que nunca llegaron: {} | peor bloque {:.2f} s".format(
            tipo, LIMITE_DOBY, sum(t[2] > 0 for t in x), len(x), sum(t[3] for t in x), max(t[1] for t in x)))


if __name__ == "__main__":
    main()
