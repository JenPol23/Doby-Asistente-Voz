"""
escuchar_voz.py  -  CORRE EN EL PC (py del sistema; no necesita la ESP32)
Reproduce en los parlantes del PC las voces de voz_cache_f5/ por persona y frase.

Uso (desde la carpeta del proyecto):
  py entrenamiento/escuchar_voz.py --piloto [--persona jenpol] [--referencia jenpol_refF2] [--frase saludo_1] [--real]
  py entrenamiento/escuchar_voz.py --persona jenpol [--frase saludo_1] [--alternativas | --revisar]
  py entrenamiento/escuchar_voz.py ... --parlante     # en vez del PC, por el parlante de la ESP32 (cerrar Doby antes)

--real: antes de cada referencia de la prueba piloto, el clip REAL con el que se clono.
--parlante usa entrenamiento/reproducir_en_parlante.py (con --tal-cual: los audios ya estan a 16 kHz).
"""

import argparse
import glob
import os
import subprocess
import sys
import winsound

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA = os.path.join(RAIZ, "voz_cache_f5")


def archivos_piloto(args):
    personas = [args.persona] if args.persona else sorted(
        d for d in os.listdir(os.path.join(CARPETA, "_piloto")) if os.path.isdir(os.path.join(CARPETA, "_piloto", d)))
    lista = []
    for p in personas:
        reales = sorted(glob.glob(os.path.join(CARPETA, "_piloto", p, "*_REAL.wav")))
        for real in reales:
            clip = os.path.basename(real)[:-len("_REAL.wav")]
            if args.referencia and clip != args.referencia:
                continue
            if args.real:
                lista.append(real)
            patron = "{}_{}.wav".format(clip, args.frase) if args.frase else clip + "_*.wav"
            lista += [a for a in sorted(glob.glob(os.path.join(CARPETA, "_piloto", p, patron))) if not a.endswith("_REAL.wav")]
    return lista


def archivos_cache(args):
    if not args.persona:
        sys.exit("Falta --persona (o usa --piloto).")
    sub = "_alternativas" if args.alternativas else "_revisar_de_oido" if args.revisar else ""
    patron = "{}_*.wav".format(args.frase) if args.frase else "*.wav"
    return sorted(glob.glob(os.path.join(CARPETA, args.persona, sub, patron)))


def main():
    parser = argparse.ArgumentParser(description="Escuchar las voces F5 de Doby")
    parser.add_argument("--piloto", action="store_true")
    parser.add_argument("--persona")
    parser.add_argument("--frase", help="clave de la frase (ej. saludo_1)")
    parser.add_argument("--referencia", help="solo piloto: clip de referencia (ej. jenpol_refF2)")
    parser.add_argument("--real", action="store_true", help="solo piloto: tambien el clip real de referencia")
    parser.add_argument("--alternativas", action="store_true")
    parser.add_argument("--revisar", action="store_true")
    parser.add_argument("--parlante", action="store_true", help="por el parlante de la ESP32")
    args = parser.parse_args()

    lista = archivos_piloto(args) if args.piloto else archivos_cache(args)
    if not lista:
        sys.exit("No hay audios con esos filtros.")
    if args.parlante:
        generados = [a for a in lista if not a.endswith("_REAL.wav")]
        if len(generados) < len(lista):
            print("(Los clips REAL no se envian al parlante: van a su frecuencia original.)")
        subprocess.run([sys.executable, os.path.join(RAIZ, "entrenamiento", "reproducir_en_parlante.py"),
                        "--tal-cual"] + generados)
        return
    for ruta in lista:
        print("  >", os.path.relpath(ruta, RAIZ))
        winsound.PlaySound(ruta, winsound.SND_FILENAME)


if __name__ == "__main__":
    main()
