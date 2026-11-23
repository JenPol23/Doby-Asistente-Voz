"""
verificar_cobertura.py  -  CORRE EN EL PC, SIN ESP32
Comprueba que no falte NINGUN audio antes de activar VOZ_CLONADA (debe dar 100 %):
- voz clonada: cada integrante enrolado (modelos/hablantes/hablantes.json) x cada frase de Doby + la
  generica, en <config.CARPETA_VOZ_CLONADA>/<persona>/; lo que sigue en _revisar_de_oido/ cuenta como faltante;
- voz normal: todas las frases en voz_cache/ (suenan cuando no hay persona verificada);
- cada WAV: abre, mono, 16 bits, 16 kHz, no es silencio ni demasiado corto, pico = config.VOLUMEN.
Es la misma comprobacion que hace Doby al arrancar (voz_clonada.cobertura).

Uso:  py pruebas/verificar_cobertura.py [--carpeta voz_cache_f5]     (codigo de salida 1 si no es 100 %)
"""

import argparse
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))

import config          # noqa: E402
import voz_clonada     # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Cobertura de las voces de Doby")
    parser.add_argument("--carpeta", help="carpeta de voz clonada (por defecto config.CARPETA_VOZ_CLONADA)")
    args = parser.parse_args()
    if args.carpeta:
        config.CARPETA_VOZ_CLONADA = args.carpeta
    ok, lineas = voz_clonada.cobertura()
    print("\n".join(lineas))
    print("\nRESULTADO: {}".format("100 % - se puede activar VOZ_CLONADA" if ok else "FALLA - NO activar VOZ_CLONADA"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
