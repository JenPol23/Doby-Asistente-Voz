"""
probar_hablante.py  -  CORRE EN EL PC (con la ESP32, sin arrancar Doby)
Calibracion en el salon: graba N segundos con el INMP441 (misma captura que grabar_inmp441.py),
aplica preparar() y muestra la similitud con cada integrante, la duracion de voz detectada y
la decision de Doby. En bucle: Enter para otra toma, q para salir.

Uso:  py entrenamiento/probar_hablante.py                    # 3 s por toma
      py entrenamiento/probar_hablante.py --seg 4 --persona jenpol --guardar
  --persona: ademas, decision de una ORDEN con esa persona_activa (regla de sesion, config.UMBRAL_SESION)
  --guardar: WAV crudo + fila en datos_voz/pruebas_hablante/registro.csv (para ajustar umbrales).
             Si la etiqueta empieza con el nombre de un integrante ("jenpol salon"), la toma puede
             sumarse al enrolamiento: py entrenamiento/enrolar_hablantes.py --incluir-pruebas
"""

import argparse
import csv
import os
import sys
import time
import wave
from datetime import datetime

import numpy as np

from grabar_inmp441 import RAIZ, a_pcm16, conectar_con_ping, grabar, pico_dbfs, revisar_huecos  # pone pc/ en sys.path
import config
import hablantes as h
from entrada_audio import EntradaAudio
from esp32_cliente import Esp32Cliente

CARPETA = os.path.join(RAIZ, "datos_voz", "pruebas_hablante")
COLUMNAS = ["fecha", "archivo", "etiqueta", "seg_voz", "pico_voz_dbfs", "similitudes", "mejor", "similitud",
            "llamado", "orden_sesion", "huecos"]


def decision_orden(sims, persona, alto):
    """Regla de sesion de Doby (pc/verificador.py) para una orden con persona_activa."""
    mejor = max(sims, key=sims.get)
    if mejor == persona and sims[mejor] >= config.UMBRAL_SESION:
        return "aceptada"
    if mejor != persona and sims[mejor] >= alto:
        return "rechazada: otro integrante ({}), debe decir Hola Doby".format(mejor)
    return "rechazada"


def main():
    parser = argparse.ArgumentParser(description="Similitud de voz en vivo con el INMP441 (sin Doby).")
    parser.add_argument("--seg", type=float, default=3.0, help="segundos por toma (3)")
    parser.add_argument("--persona", help="persona_activa para ver la decision de una orden")
    parser.add_argument("--guardar", action="store_true", help="guardar cada toma y su resultado")
    args = parser.parse_args()

    nombres, centroides, cfg = h.cargar_hablantes()
    alto, bajo = cfg["umbral_alto"], cfg["umbral_bajo"]
    if args.persona and args.persona not in nombres:
        parser.error("--persona debe ser una de: {}".format(", ".join(nombres)))
    print("Cargando ECAPA...")
    modelo = h.cargar_modelo()
    h.embedding(modelo, (1e-4 * np.random.default_rng(0).standard_normal(h.TASA)).astype(np.float32))

    esp = Esp32Cliente()
    if not conectar_con_ping(esp):
        sys.exit("La ESP32 no responde en {}:{} (revisa que Doby no este conectado).".format(esp.ip, esp.puerto))
    entrada = EntradaAudio(esp)
    if args.guardar:
        os.makedirs(CARPETA, exist_ok=True)
    print("Integrantes: {}   umbrales: alto {:.3f}, bajo {:.3f}, sesion {:.3f}".format(
        ", ".join(nombres), alto, bajo, config.UMBRAL_SESION))
    print("Para enrolar en sitio: usa --guardar y empieza la etiqueta con el nombre (ej. 'jenpol salon').")
    try:
        n = 0
        while True:
            r = input("\n[Enter] grabar {:g} s, o escribe una etiqueta (ej. 'jenpol 2m') y Enter, [q] salir: ".format(
                args.seg)).strip()
            if r.lower() == "q":
                break
            bloques, llegadas, reconexiones = grabar(entrada, args.seg)
            pcm = a_pcm16(bloques, args.seg)
            avisos, _ = revisar_huecos(llegadas, reconexiones)
            voz = h.tramo_voz(pcm)
            listo = h.preparar(pcm)
            if listo is None:
                print("  Sin voz suficiente (menos de {} s).".format(h.VOZ_MINIMA))
                continue
            t = time.perf_counter()
            e = h.embedding(modelo, listo)
            ms = 1000 * (time.perf_counter() - t)
            sims = {nombre: float(v) for nombre, v in zip(nombres, centroides @ e)}
            llamado = h.identificar(e, centroides, nombres, alto, bajo)["estado"]
            orden = decision_orden(sims, args.persona, alto) if args.persona else ""
            seg_voz = voz[1] - voz[0] if voz else 0.0
            pico = pico_dbfs(h.pasa_altos(pcm))
            print("  Voz detectada: {:.2f} s   pico voz {:.1f} dBFS   ({:.0f} ms)".format(seg_voz, pico, ms))
            for nombre, s in sorted(sims.items(), key=lambda x: -x[1]):
                marca = "  <- alto" if s >= alto else "  <- zona gris" if s >= bajo else ""
                print("    {:8s} {:6.3f} {}{}".format(nombre, s, "#" * max(0, int(40 * s)), marca))
            print("  Llamado 'Hola Doby': {}{}".format(llamado.upper(),
                  "   Orden con persona_activa={}: {}".format(args.persona, orden.upper()) if orden else ""))
            if avisos:
                print("  ATENCION, huecos en la captura: " + "; ".join(avisos))
            if args.guardar:
                n += 1
                nombre = "prueba_{}_{:03d}.wav".format(datetime.now().strftime("%Y%m%d_%H%M%S"), n)
                with wave.open(os.path.join(CARPETA, nombre), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(h.TASA); w.writeframes(pcm.astype("<i2").tobytes())
                ruta_csv = os.path.join(CARPETA, "registro.csv")
                nuevo = not os.path.exists(ruta_csv)
                with open(ruta_csv, "a", newline="", encoding="utf-8-sig") as f:
                    escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
                    if nuevo:
                        escritor.writeheader()
                    mejor = max(sims, key=sims.get)
                    escritor.writerow({"fecha": datetime.now().isoformat(sep=" ", timespec="seconds"), "archivo": nombre,
                                       "etiqueta": r, "seg_voz": "{:.2f}".format(seg_voz), "pico_voz_dbfs": "{:.1f}".format(pico),
                                       "similitudes": ";".join("{}={:.4f}".format(k, v) for k, v in sims.items()),
                                       "mejor": mejor, "similitud": "{:.4f}".format(sims[mejor]), "llamado": llamado,
                                       "orden_sesion": orden, "huecos": "; ".join(avisos) or "no"})
                print("  Guardado:", nombre)
    except KeyboardInterrupt:
        print()
    finally:
        esp.cerrar()


if __name__ == "__main__":
    main()
