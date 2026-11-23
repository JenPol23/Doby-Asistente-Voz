"""
grabar_inmp441.py  -  CORRE EN EL PC
Graba voces con el microfono INMP441 de la ESP32 (orden MIC del protocolo),
con la MISMA captura y conversion que usa Doby.

DEPENDENCIA: usa EntradaAudio._bloque() y EntradaAudio.vaciar() de
pc/entrada_audio.py tal como estan (sin modificarlos):
  - 2 pedidos MIC en vuelo, reconexion si se cae el socket
  - conversion: (int32 >> 16) -> float32
Y repite el final de EntradaAudio.escuchar_frase(): quitar la media y / 32768.
Si esos metodos cambian, revisar este script.

El WAV se guarda SIN ganancia y SIN filtro: mono, 16 kHz, int16 = round(audio * 32768).
El informe de cada toma mide el pico de la voz con preproceso.pasa_altos()
(100 Hz, el mismo filtro de enrolar e identificar) y avisa de saturacion,
golpes de aire (20-100 Hz) y voz muy baja.

Uso:
  py entrenamiento/grabar_inmp441.py --prueba                    # 10 s seguidos
  py entrenamiento/grabar_inmp441.py --prueba --seg 20
  py entrenamiento/grabar_inmp441.py --persona jenpol --bloque A  # 15 "Hola Doby", 3 s
  py entrenamiento/grabar_inmp441.py --persona jenpol --bloque B  # 22 ordenes, 4 s
  py entrenamiento/grabar_inmp441.py --persona jenpol --bloque B --desde 7

Frases: datos/guion_voces/guion_voces.json
Salida: datos_voz/inmp441/<persona>/<persona>_<bloque>_<nn>.wav
        datos_voz/inmp441/<persona>/<persona>_grabaciones.csv
"""

import argparse
import csv
import io
import json
import math
import os
import re
import socket
import sys
import time
import wave
import winsound
from datetime import datetime

import numpy as np
from scipy.signal import butter, sosfiltfilt

from preproceso import pasa_altos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))

import config                                            # noqa: E402
from entrada_audio import EntradaAudio, SEG_BLOQUE       # noqa: E402
from esp32_cliente import Esp32Cliente                   # noqa: E402

CARPETA_DATOS = os.path.join(RAIZ, "datos_voz", "inmp441")
RUTA_GUION = os.path.join(RAIZ, "datos", "guion_voces", "guion_voces.json")
FRASES_ESPERADAS = {"A": 15, "B": 22, "D": 12}
SEG_VENTANA = {"A": 3.0, "B": 4.0}
SEG_PRUEBA = 10.0
COLUMNAS_CSV = ["archivo", "frase", "indicacion", "pico_dbfs", "pico_voz_dbfs", "huecos", "fecha"]

TIMEOUT_PING = 3.0            # la ESP32 acepta un PC nuevo tras 1 s sin ordenes
SEG_CUENTA = 3                # cuenta regresiva (se lee y descarta el microfono)
HUECO_BLOQUE = 0.25           # ibuf=16000 bytes = 4000 muestras int32 = 250 ms en la ESP32
HUECO_TOTAL = 0.10            # tiempo real - duracion de las muestras
GANANCIA_ESCUCHA = 20.0       # solo para reproducir; el WAV no la lleva

DBFS_SATURACION = -1.0        # pico total (crudo)
DB_GOLPE = 6.0                # banda 20-100 Hz sobre el pico voz
BANDA_GOLPE = (20, 100)       # Hz; bajo 20 Hz es el vaiven de la fuente: se ignora
DBFS_VOZ_BAJA = -30.0         # pico voz (pasa altos 100 Hz)


# ---------------- Conexion ----------------
def conectar_con_ping(esp):
    """
    Un solo intento de conexion + PING (Esp32Cliente.conectar() reintenta para
    siempre). Deja esp.sock y esp.lector listos, igual que conectar().
    """
    try:
        sock = socket.create_connection((esp.ip, esp.puerto), timeout=TIMEOUT_PING)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        esp.sock = sock
        esp.lector = sock.makefile("rb")
        sock.sendall(b"PING\n")
        return esp.lector.readline().strip() == b"PONG"
    except OSError:
        esp.cerrar()
        return False


# ---------------- Captura ----------------
def grabar(entrada, segundos):
    """
    Cuenta regresiva leyendo y descartando el microfono (vacia el audio viejo
    del bufer de la ESP32 y deja los MIC en vuelo), luego graba 'segundos'.
    Devuelve (bloques, llegadas, reconexiones): llegadas[0] es el ultimo bloque
    descartado y llegadas[i] el instante en que llego bloques[i - 1].
    """
    for n in range(SEG_CUENTA, 0, -1):
        print("  {}...".format(n))
        fin = time.perf_counter() + 1.0
        while time.perf_counter() < fin:
            entrada._bloque()
    print("  >>> GRABANDO {:g} s <<<".format(segundos))

    total = int(math.ceil(segundos / SEG_BLOQUE))
    bloques = []
    llegadas = [time.perf_counter()]
    reconexiones = 0
    sock = entrada.esp.sock
    for _ in range(total):
        muestras, _nivel = entrada._bloque()
        llegadas.append(time.perf_counter())
        bloques.append(muestras)
        if entrada.esp.sock is not sock:          # _bloque() reconecto: hubo hueco
            reconexiones += 1
            sock = entrada.esp.sock
    entrada.vaciar()
    print("  >>> FIN <<<")
    return bloques, llegadas, reconexiones


def a_pcm16(bloques, segundos):
    """Igual que el final de escuchar_frase() y luego a int16 sin ganancia."""
    audio = np.concatenate(bloques)[:int(round(segundos * config.TASA))]
    audio -= audio.mean()                          # quita el desnivel de continua
    audio = audio / 32768.0                        # float32 en [-1, 1], como para Whisper
    return np.clip(np.round(audio * 32768.0), -32768, 32767).astype(np.int16)


def pico_dbfs(audio):
    """Pico en dBFS de un audio en escala int16 (int16 o float)."""
    pico = float(np.max(np.abs(np.asarray(audio, dtype=np.float64)))) if len(audio) else 0.0
    return 20 * math.log10(pico / 32768.0) if pico > 0 else float("-inf")


def revisar_niveles(pcm):
    """Devuelve (pico voz, pico total, pico graves 20-100 Hz, avisos) en dBFS."""
    voz = pico_dbfs(pasa_altos(pcm, fs=config.TASA))
    total = pico_dbfs(pcm)
    sos = butter(4, BANDA_GOLPE, btype="bandpass", fs=config.TASA, output="sos")
    graves = pico_dbfs(sosfiltfilt(sos, pcm.astype(np.float64)))
    avisos = []
    if total > DBFS_SATURACION:
        avisos.append("SATURACIÓN, repite con [r]")
    if voz < DBFS_VOZ_BAJA:
        avisos.append("VOZ MUY BAJA, acércate un poco")
    elif graves - voz > DB_GOLPE:          # con voz muy baja, el vaiven que se cuela bajo 20 Hz lo dispararia
        avisos.append("GOLPE DE AIRE, aléjate o habla de lado, repite con [r]")
    return voz, total, graves, avisos


def revisar_huecos(llegadas, reconexiones):
    """Devuelve (lista de avisos, resumen) comparando tiempo real y muestras."""
    intervalos = np.diff(llegadas)
    real = llegadas[-1] - llegadas[0]
    esperado = len(intervalos) * SEG_BLOQUE
    avisos = []
    for i, dt in enumerate(intervalos):
        if dt > HUECO_BLOQUE:
            avisos.append("posible corte en t = {:.2f} s (bloque tardo {:.0f} ms)".format(
                i * SEG_BLOQUE, dt * 1000))
    if real - esperado > HUECO_TOTAL:
        avisos.append("el tiempo real supera al audio en {:.0f} ms: se perdieron muestras".format(
            (real - esperado) * 1000))
    if reconexiones:
        avisos.append("{} reconexion(es) durante la toma".format(reconexiones))
    resumen = "tiempo real {:.3f} s / audio {:.3f} s / mayor intervalo {:.0f} ms (normal {:.0f} ms)".format(
        real, esperado, float(intervalos.max()) * 1000, SEG_BLOQUE * 1000)
    return avisos, resumen


def informe(pcm, llegadas, reconexiones, detallado=False):
    """Imprime picos, avisos de nivel y huecos. Devuelve todos los avisos."""
    voz, total, graves, avisos_nivel = revisar_niveles(pcm)
    print("  Pico voz: {:.1f} dBFS   Pico total: {:.1f} dBFS   (graves 20-100 Hz: {:.1f} dBFS)".format(
        voz, total, graves))
    for aviso in avisos_nivel:
        print("  >>", aviso)

    avisos_huecos, resumen = revisar_huecos(llegadas, reconexiones)
    if detallado or avisos_huecos:
        print("  " + resumen)
    if avisos_huecos:
        print("  ATENCION, posibles huecos en la captura:")
        for aviso in avisos_huecos:
            print("    -", aviso)
    else:
        print("  Sin huecos detectados.")
    return avisos_nivel + avisos_huecos


# ---------------- WAV ----------------
def wav_bytes(pcm):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(config.TASA)
        wav.writeframes(pcm.astype("<i2").tobytes())
    return buf.getvalue()


def guardar_wav(ruta, pcm):
    with open(ruta, "wb") as f:
        f.write(wav_bytes(pcm))


def escuchar(pcm):
    """Reproduce con ganancia para oirlo bien (el archivo guardado no cambia)."""
    pico = float(np.max(np.abs(pcm.astype(np.float32)))) if len(pcm) else 0.0
    ganancia = min(GANANCIA_ESCUCHA, 30000.0 / pico) if pico > 0 else 1.0
    alto = np.clip(pcm.astype(np.float32) * ganancia, -32768, 32767).astype(np.int16)
    print("  Reproduciendo (ganancia de escucha x{:.1f})...".format(ganancia))
    winsound.PlaySound(wav_bytes(alto), winsound.SND_MEMORY)


# ---------------- Guion y CSV ----------------
def cargar_guion():
    """Lee guion_voces.json y verifica que A, B y D tengan sus frases numeradas 1..N."""
    with open(RUTA_GUION, encoding="utf-8") as f:
        guion = json.load(f)
    for bloque, cantidad in FRASES_ESPERADAS.items():
        numeros = [fr["n"] for fr in guion["bloques"][bloque]["frases"]]
        if numeros != list(range(1, cantidad + 1)):
            sys.exit("{}: el bloque {} debe tener {} frases numeradas 1..{} (tiene {}).".format(
                os.path.relpath(RUTA_GUION, RAIZ), bloque, cantidad, cantidad, len(numeros)))
    return guion


def actualizar_csv(ruta_csv, fila):
    """Agrega la fila; si el archivo ya estaba (regrabado), reemplaza su fila anterior."""
    filas = []
    if os.path.exists(ruta_csv):
        with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
            filas = [r for r in csv.DictReader(f) if r["archivo"] != fila["archivo"]]
    filas.append(fila)
    filas.sort(key=lambda r: r["archivo"])
    while True:
        try:
            with open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
                escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CSV)
                escritor.writeheader()
                escritor.writerows(filas)
            return
        except PermissionError:
            input("  No se pudo escribir {} (abierto en Excel?). Cierralo y presiona Enter...".format(
                os.path.basename(ruta_csv)))


def preguntar(texto, validas):
    while True:
        respuesta = input(texto).strip().lower()
        if respuesta in validas:
            return respuesta


# ---------------- Modo bloque (A / B) ----------------
def grabar_frase(entrada, frase, total, ruta_wav, ruta_csv, segundos):
    """Graba una frase hasta que el usuario la acepte. Devuelve 'siguiente' o 'salir'."""
    indicacion = frase.get("indicacion", "")
    print()
    print("[{}/{}]  {}".format(frase["n"], total, frase["texto"]))
    if indicacion:
        print("        Indicacion: {}".format(indicacion))

    if os.path.exists(ruta_wav):
        r = preguntar("  {} ya existe. [s] regrabar, [Enter] saltar, [q] salir: ".format(
            os.path.basename(ruta_wav)), ("s", "", "q"))
        if r == "":
            return "siguiente"
        if r == "q":
            return "salir"

    while True:
        if preguntar("  [Enter] grabar ({:g} s), [q] salir: ".format(segundos), ("", "q")) == "q":
            return "salir"
        bloques, llegadas, reconexiones = grabar(entrada, segundos)
        pcm = a_pcm16(bloques, segundos)
        avisos = informe(pcm, llegadas, reconexiones)

        if reconexiones:
            print("  Se perdio la conexion con la ESP32 durante la toma: NO se guarda.")
            if preguntar("  [Enter] repetir esta frase, [q] salir: ", ("", "q")) == "q":
                return "salir"
            continue

        while True:
            r = preguntar("  [Enter] guardar y seguir, [r] repetir, [e] escuchar, [q] guardar y salir: ",
                          ("", "r", "e", "q"))
            if r != "e":
                break
            escuchar(pcm)
        if r == "r":
            continue

        guardar_wav(ruta_wav, pcm)
        pico = pico_dbfs(pcm)
        pico_voz = pico_dbfs(pasa_altos(pcm, fs=config.TASA))
        actualizar_csv(ruta_csv, {
            "archivo": os.path.basename(ruta_wav),
            "frase": frase["texto"],
            "indicacion": indicacion,
            "pico_dbfs": "{:.1f}".format(pico) if math.isfinite(pico) else "-inf",
            "pico_voz_dbfs": "{:.1f}".format(pico_voz) if math.isfinite(pico_voz) else "-inf",
            "huecos": "; ".join(avisos) if avisos else "no",
            "fecha": datetime.now().isoformat(sep=" ", timespec="seconds"),
        })
        print("  Guardado:", os.path.relpath(ruta_wav, RAIZ))
        return "salir" if r == "q" else "siguiente"


def modo_bloque(entrada, guion, persona, bloque, segundos, desde):
    info = guion["bloques"][bloque]
    frases = info["frases"]
    carpeta = os.path.join(CARPETA_DATOS, persona)
    os.makedirs(carpeta, exist_ok=True)
    ruta_csv = os.path.join(carpeta, "{}_grabaciones.csv".format(persona))

    def ruta_wav(n):
        return os.path.join(carpeta, "{}_{}_{:02d}.wav".format(persona, bloque, n))

    if desde is None:
        faltan = [fr["n"] for fr in frases if not os.path.exists(ruta_wav(fr["n"]))]
        if not faltan:
            print("El bloque {} de {} ya esta completo ({} frases). Usa --desde N para regrabar.".format(
                bloque, persona, len(frases)))
            return
        desde = faltan[0]

    print()
    print("Persona: {}   Bloque {}: {}   Ventana: {:g} s   Desde la frase {} de {}".format(
        persona, bloque, info["descripcion"], segundos, desde, len(frases)))

    for frase in frases[desde - 1:]:
        if grabar_frase(entrada, frase, len(frases), ruta_wav(frase["n"]), ruta_csv, segundos) == "salir":
            break

    grabadas = sum(os.path.exists(ruta_wav(fr["n"])) for fr in frases)
    print()
    print("Bloque {} de {}: {} de {} frases grabadas.".format(bloque, persona, grabadas, len(frases)))


# ---------------- Modo prueba ----------------
def modo_prueba(entrada, segundos):
    carpeta = os.path.join(CARPETA_DATOS, "_prueba")
    os.makedirs(carpeta, exist_ok=True)
    archivo = os.path.join(carpeta, "prueba_{}.wav".format(datetime.now().strftime("%Y%m%d_%H%M%S")))

    print()
    print("PRUEBA: {:g} s de habla continua (lee un texto en voz alta sin parar).".format(segundos))
    input("Presiona Enter para empezar...")
    bloques, llegadas, reconexiones = grabar(entrada, segundos)
    pcm = a_pcm16(bloques, segundos)
    guardar_wav(archivo, pcm)

    print()
    print("  Guardado en", os.path.relpath(archivo, RAIZ))
    informe(pcm, llegadas, reconexiones, detallado=True)
    escuchar(pcm)


def main():
    parser = argparse.ArgumentParser(description="Graba voces con el INMP441 de la ESP32.")
    parser.add_argument("--prueba", action="store_true", help="graba habla continua para revisar cortes")
    parser.add_argument("--persona", help="nombre de la persona (ej. jenpol, impostor_01)")
    parser.add_argument("--bloque", type=str.upper, choices=sorted(SEG_VENTANA), help="bloque del guion")
    parser.add_argument("--desde", type=int, help="numero de frase donde empezar")
    parser.add_argument("--seg", type=float,
                        help="segundos por toma (prueba 10, A 3, B 4)")
    args = parser.parse_args()

    if not args.prueba:
        if not args.persona or not args.bloque:
            parser.error("falta --persona y --bloque (o usa --prueba)")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", args.persona):
            parser.error("--persona solo admite letras, numeros, _ y -")
        guion = cargar_guion()
        cantidad = FRASES_ESPERADAS[args.bloque]
        if args.desde is not None and not 1 <= args.desde <= cantidad:
            parser.error("--desde debe estar entre 1 y {} en el bloque {}".format(cantidad, args.bloque))

    esp = Esp32Cliente()
    print("PING a la ESP32 en {}:{}...".format(esp.ip, esp.puerto))
    if not conectar_con_ping(esp):
        print("La ESP32 no responde en {}:{}.".format(esp.ip, esp.puerto))
        print("Revisa que este encendida y en la misma red, que IP_ESP32 de pc/config.py")
        print("sea la correcta y que Doby (u otro script) no este conectado a ella.")
        sys.exit(1)
    print("PONG: ESP32 lista.")

    entrada = EntradaAudio(esp)
    try:
        if args.prueba:
            modo_prueba(entrada, args.seg or SEG_PRUEBA)
        else:
            modo_bloque(entrada, guion, args.persona, args.bloque,
                        args.seg or SEG_VENTANA[args.bloque], args.desde)
    except KeyboardInterrupt:
        print("\nInterrumpido. Lo ya guardado queda en disco.")
    finally:
        esp.cerrar()


if __name__ == "__main__":
    main()
