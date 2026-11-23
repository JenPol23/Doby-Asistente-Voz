"""
grabar_ruido.py  -  CORRE EN EL PC
Graba el ruido de los aparatos con el INMP441 de la ESP32 (para aumento de
datos) y sirve como chequeo del hardware antes de la presentacion.

Uso:
  py entrenamiento/grabar_ruido.py --lugar cuarto
  py entrenamiento/grabar_ruido.py --lugar salon --seg 20
  py entrenamiento/grabar_ruido.py --lugar cuarto --solo ventilador,todos

Captura: la de grabar_inmp441.py (misma conversion que Doby; WAV crudo mono
16 kHz int16). Reles: Esp32Cliente.rele() (RELE <k> <1|0>).

SEGURIDAD: si el PC se desconecta, el firmware solo apaga el cautin y la plancha
(tras 15 s); el ventilador y el bombillo conservan su estado.
Al iniciar y al terminar (normal, [q], Ctrl+C o error) se envia TODOS 0 por
una conexion NUEVA (sin respuestas MIC pendientes) con intentos limitados:
Esp32Cliente.todos_apagados() no sirve aqui porque reconecta para siempre.
El cautin y la plancha no hacen ruido, pero se graban por si su resistencia
mete interferencia electrica en el microfono. Las grabaciones viejas con el
carro (ruido_<lugar>_carro_*, ventilador_carro_*) se conservan: las usa
conjunto_hablantes.py.

Salida: datos_voz/ruido/<lugar>/ruido_<lugar>_<condicion>_<nn>.wav
        datos_voz/ruido/<lugar>/ruido_<lugar>.csv
"""

import argparse
import csv
import glob
import math
import os
import re
import sys
import time
from datetime import datetime

import numpy as np

from grabar_inmp441 import (RAIZ, CARPETA_DATOS as CARPETA_VOZ, a_pcm16, conectar_con_ping,
                            grabar, guardar_wav, pico_dbfs, revisar_huecos)
from preproceso import pasa_altos

import config                                            # noqa: E402  (pc/ en sys.path por grabar_inmp441)
from entrada_audio import EntradaAudio                   # noqa: E402
from esp32_cliente import Esp32Cliente                   # noqa: E402

CARPETA_RUIDO = os.path.join(RAIZ, "datos_voz", "ruido")
COLUMNAS_CSV = ["archivo", "condicion", "reles", "funciono", "rms_dbfs", "pico_dbfs",
                "rms_filtrado_dbfs", "huecos", "fecha"]

# (condicion, aparatos encendidos, murmullo del celular)
CONDICIONES = [
    ("base", [], False),
    ("ventilador", ["ventilador"], False),
    ("bombillo", ["bombillo"], False),
    ("cautin", ["cautin"], False),
    ("plancha", ["plancha"], False),
    ("todos", ["ventilador", "bombillo", "cautin", "plancha"], False),
    ("murmullo", [], True),
    ("todos_murmullo", ["ventilador", "bombillo", "cautin", "plancha"], True),
]

INTENTOS_APAGADO = 3
INTENTOS_GRABAR = 3           # si hay reconexion durante la toma, se repite sola
MARGEN_RIESGO = 15.0          # dB de la voz sobre el ruido (pico contra pico)


# ---------------- Reles ----------------
def apagar_todo_seguro(esp):
    """
    TODOS 0 por una conexion nueva, con intentos limitados. True si la ESP32
    respondio OK. Deja esp conectado (listo para seguir) si lo logra.
    """
    for intento in range(1, INTENTOS_APAGADO + 1):
        try:
            esp.cerrar()
            if conectar_con_ping(esp) and esp._orden_linea("TODOS 0") == "OK":
                return True
        except KeyboardInterrupt:
            print("  (Ctrl+C ignorado: primero hay que apagar los reles)")
        except (OSError, UnicodeDecodeError):
            pass
        print("  No se pudo confirmar el apagado (intento {}/{}).".format(intento, INTENTOS_APAGADO))
        try:
            time.sleep(1.0)
        except KeyboardInterrupt:
            print("  (Ctrl+C ignorado: primero hay que apagar los reles)")
    esp.cerrar()
    return False


def mover_reles(esp, reles, estado):
    """Enciende o apaga cada rele con Esp32Cliente.rele(). Devuelve los que no dieron OK."""
    return [k for k in reles if not esp.rele(k, estado)]


def texto_reles(aparatos):
    if not aparatos:
        return "todo apagado"
    return ", ".join("{} (rele {})".format(a, config.APARATOS[a]) for a in aparatos)


# ---------------- Niveles ----------------
def rms_dbfs(audio):
    audio = np.asarray(audio, dtype=np.float64)
    rms = float(np.sqrt(np.mean(audio ** 2))) if len(audio) else 0.0
    return 20 * math.log10(rms / 32768.0) if rms > 0 else float("-inf")


def db(valor):
    return "{:.1f}".format(valor) if valor is not None and math.isfinite(valor) else "-inf"


def voz_referencia(persona):
    """Mediana de pico_voz_dbfs de la persona, o None si no hay datos."""
    ruta = os.path.join(CARPETA_VOZ, persona, "{}_grabaciones.csv".format(persona))
    if not os.path.exists(ruta):
        return None
    valores = []
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            try:
                valor = float(fila.get("pico_voz_dbfs") or "nan")
            except ValueError:
                continue
            if math.isfinite(valor):
                valores.append(valor)
    return float(np.median(valores)) if valores else None


# ---------------- Archivos ----------------
def siguiente_wav(carpeta, lugar, condicion):
    """Primer ruido_<lugar>_<condicion>_<nn>.wav libre (nunca sobrescribe)."""
    base = "ruido_{}_{}_".format(lugar, condicion)
    usados = [int(m.group(1)) for m in
              (re.fullmatch(re.escape(base) + r"(\d+)\.wav", os.path.basename(r))
               for r in glob.glob(os.path.join(carpeta, base + "*.wav"))) if m]
    return os.path.join(carpeta, "{}{:02d}.wav".format(base, max(usados, default=0) + 1))


def agregar_fila(ruta_csv, fila):
    nuevo = not os.path.exists(ruta_csv)
    while True:
        try:
            with open(ruta_csv, "a", newline="", encoding="utf-8-sig") as f:
                escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
                if nuevo:
                    escritor.writeheader()
                escritor.writerow(fila)
            return
        except PermissionError:
            input("  No se pudo escribir {} (abierto en Excel?). Cierralo y presiona Enter...".format(
                os.path.basename(ruta_csv)))


def preguntar(texto, validas):
    while True:
        respuesta = input(texto).strip().lower()
        if respuesta in validas:
            return respuesta


# ---------------- Una condicion ----------------
def correr_condicion(esp, entrada, condicion, numero, total, args, carpeta, ruta_csv, voz):
    """Devuelve el resultado para el resumen, None si se salto o 'salir'."""
    nombre, aparatos, murmullo = condicion
    reles = [config.APARATOS[a] for a in aparatos]
    fila = {"archivo": "", "condicion": nombre, "reles": "+".join(map(str, reles)) or "ninguno",
            "funciono": "sí", "rms_dbfs": "", "pico_dbfs": "", "rms_filtrado_dbfs": "", "huecos": ""}
    resultado = {"condicion": nombre, "funciono": "sí", "rms_filtrado": None, "margen": None}

    print()
    print("[{}/{}] {}: {}{}".format(numero, total, nombre, texto_reles(aparatos),
                                    " + murmullo del celular" if murmullo else ""))
    r = preguntar("  [Enter] seguir, [s] saltar, [q] salir: ", ("", "s", "q"))
    if r == "s":
        return None
    if r == "q":
        return "salir"

    if any(a in config.CALIENTES for a in aparatos):
        input("  Deja el cautín en su base y la plancha sobre una superficie que aguante el calor,"
              " sin nada encima; no los dejes solos. Presiona Enter")

    if reles:
        sin_ok = mover_reles(esp, reles, 1)
        time.sleep(args.espera)
        if sin_ok:
            print("  La ESP32 no respondio OK al encender el/los rele(s) {}.".format(sin_ok))
            funciono = False
        else:
            funciono = preguntar("  ¿Encendió correctamente? [Enter] sí / [n] no: ", ("", "n")) == ""
        if not funciono:
            mover_reles(esp, reles, 0)
            fila.update(funciono="FALLA", fecha=datetime.now().isoformat(sep=" ", timespec="seconds"))
            agregar_fila(ruta_csv, fila)
            print("  FALLA anotada; apague esos reles y sigo con la siguiente condicion.")
            resultado["funciono"] = "FALLA"
            return resultado

    if murmullo:
        input("  Reproduce ruido de salón en el celular a unos 2 m y presiona Enter")

    print("  No hables durante la grabacion.")
    for intento in range(1, INTENTOS_GRABAR + 1):
        bloques, llegadas, reconexiones = grabar(entrada, args.seg)
        if not reconexiones:
            break
        print("  Se perdio la conexion con la ESP32 durante la toma (intento {}/{}).".format(
            intento, INTENTOS_GRABAR))
        if reles:
            mover_reles(esp, reles, 1)       # por si la ESP32 se reinicio y los apago
            time.sleep(args.espera)

    if reles:
        sin_ok = mover_reles(esp, reles, 0)
        if sin_ok:
            print("  ATENCION: la ESP32 no confirmo el apagado del/los rele(s) {}.".format(sin_ok))
    if murmullo:
        print("  Ya puedes detener el ruido del celular.")

    avisos, resumen = revisar_huecos(llegadas, reconexiones)
    fila["huecos"] = "; ".join(avisos) if avisos else "no"
    fila["fecha"] = datetime.now().isoformat(sep=" ", timespec="seconds")
    if reconexiones:
        print("  Reconexion en los {} intentos: NO se guarda.".format(INTENTOS_GRABAR))
        agregar_fila(ruta_csv, fila)
        return resultado

    pcm = a_pcm16(bloques, args.seg)
    filtrado = pasa_altos(pcm, fs=config.TASA)
    rms, pico = rms_dbfs(pcm), pico_dbfs(pcm)
    rms_f, pico_f = rms_dbfs(filtrado), pico_dbfs(filtrado)
    ruta_wav = siguiente_wav(carpeta, args.lugar, nombre)
    guardar_wav(ruta_wav, pcm)

    print("  Guardado:", os.path.relpath(ruta_wav, RAIZ))
    print("  Crudo:    RMS {} dBFS   pico {} dBFS".format(db(rms), db(pico)))
    print("  Filtrado: RMS {} dBFS   pico {} dBFS   (pasa altos 100 Hz)".format(db(rms_f), db(pico_f)))
    if voz is not None:
        resultado["margen"] = voz - pico_f
        print("  Tu voz quedaria ~{:.0f} dB sobre este ruido (pico contra pico).".format(resultado["margen"]))
    if avisos:
        print("  " + resumen)
        print("  ATENCION, posibles huecos en la captura:")
        for aviso in avisos:
            print("    -", aviso)
    else:
        print("  Sin huecos detectados.")

    fila.update(archivo=os.path.basename(ruta_wav), rms_dbfs=db(rms), pico_dbfs=db(pico),
                rms_filtrado_dbfs=db(rms_f))
    agregar_fila(ruta_csv, fila)
    resultado["rms_filtrado"] = rms_f
    return resultado


def imprimir_resumen(resultados, voz):
    if not resultados:
        return
    print()
    print("RESUMEN" + ("" if voz is not None else "  (sin referencia de voz: no hay margen)"))
    print("  {:18s} {:9s} {:>14s} {:>12s}".format("condicion", "funciono", "RMS filtrado", "margen voz"))
    for r in resultados:
        rms_f = "{} dBFS".format(db(r["rms_filtrado"])) if r["rms_filtrado"] is not None else "-"
        margen = "{:+.1f} dB".format(r["margen"]) if r["margen"] is not None else "-"
        riesgo = "  RIESGO" if r["margen"] is not None and r["margen"] < MARGEN_RIESGO else ""
        print("  {:18s} {:9s} {:>14s} {:>12s}{}".format(r["condicion"], r["funciono"], rms_f, margen, riesgo))


# ---------------- Principal ----------------
def main(argv=None):
    nombres = [c[0] for c in CONDICIONES]
    parser = argparse.ArgumentParser(description="Graba el ruido de los aparatos con el INMP441.")
    parser.add_argument("--lugar", required=True, help="nombre del lugar (ej. cuarto, salon)")
    parser.add_argument("--seg", type=float, default=30.0, help="segundos por condicion (30)")
    parser.add_argument("--espera", type=float, default=2.0, help="segundos tras encender los reles (2)")
    parser.add_argument("--solo", help="condicion(es) separadas por coma: " + ", ".join(nombres))
    parser.add_argument("--voz", default="jenpol", help="persona de referencia para el margen (jenpol)")
    parser.add_argument("--ip", default=config.IP_ESP32, help="IP de la ESP32 (la de pc/config.py)")
    args = parser.parse_args(argv)

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.lugar):
        parser.error("--lugar solo admite letras, numeros, _ y -")
    condiciones = CONDICIONES
    if args.solo:
        pedidas = [s.strip() for s in args.solo.split(",") if s.strip()]
        malas = [s for s in pedidas if s not in nombres]
        if malas:
            parser.error("condicion desconocida: {} (validas: {})".format(", ".join(malas), ", ".join(nombres)))
        condiciones = [c for c in CONDICIONES if c[0] in pedidas]

    carpeta = os.path.join(CARPETA_RUIDO, args.lugar)
    os.makedirs(carpeta, exist_ok=True)
    ruta_csv = os.path.join(carpeta, "ruido_{}.csv".format(args.lugar))
    voz = voz_referencia(args.voz)
    if voz is None:
        print("Sin referencia de voz de {} (no hay pico_voz_dbfs): no se calcula el margen.".format(args.voz))
    else:
        print("Referencia de voz de {}: mediana del pico voz {:.1f} dBFS.".format(args.voz, voz))

    esp = Esp32Cliente(ip=args.ip)
    print("PING y TODOS 0 a la ESP32 en {}:{}...".format(esp.ip, esp.puerto))
    if not apagar_todo_seguro(esp):
        print("La ESP32 no responde en {}:{}.".format(esp.ip, esp.puerto))
        print("Revisa que este encendida y en la misma red, que IP_ESP32 de pc/config.py")
        print("sea la correcta y que Doby (u otro script) no este conectado a ella.")
        sys.exit(1)
    print("ESP32 lista: todos los reles apagados.")

    resultados = []
    try:
        entrada = EntradaAudio(esp)
        for numero, condicion in enumerate(condiciones, 1):
            resultado = correr_condicion(esp, entrada, condicion, numero, len(condiciones),
                                         args, carpeta, ruta_csv, voz)
            if resultado == "salir":
                break
            if resultado is not None:
                resultados.append(resultado)
    except KeyboardInterrupt:
        print("\nInterrumpido con Ctrl+C.")
    finally:
        print()
        print("Apagando todos los reles (TODOS 0)...")
        if apagar_todo_seguro(esp):
            print("CONFIRMADO: la ESP32 respondio OK, todos los reles quedaron apagados.")
        else:
            print("!!! NO SE PUDO CONFIRMAR EL APAGADO: desconecta la fuente de los reles. !!!")
        esp.cerrar()
    imprimir_resumen(resultados, voz)


if __name__ == "__main__":
    main()
