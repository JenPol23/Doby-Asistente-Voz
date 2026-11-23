"""
conjunto_hablantes.py
Datos para enrolar y evaluar la verificacion de hablante (no lo usa Doby).

  personas()          integrantes (datos_voz/inmp441/<nombre>/) e impostores (impostor_NN/)
  tomas_inmp441(p)    tomas A y B con su regla de descarte (CSV de grabar_inmp441.py)
  tomas_celular(p)    segmentos del celular con uso=enrolar (CSV de validar_audios.py);
                      el bloque C se corta en ventanas de 3 s con voz
  ruidos()            ruidos del INMP441 por condicion, divididos en el tiempo:
                      60 % para aumentar el entrenamiento, 40 % para las pruebas
  division(...)       70/30 por persona y bloque, con semilla fija

Los impostores se usan SOLO para prueba: evaluar_hablantes.py y enrolar_hablantes.py
comprueban que ninguna toma de impostor entre al entrenamiento.
"""

import csv
import glob
import os
import re
import wave
import zlib

import numpy as np

import hablantes as h

DATOS = os.path.join(h.RAIZ, "datos_voz")
CARPETA_INMP441 = os.path.join(DATOS, "inmp441")
CARPETA_PROCESADOS = os.path.join(DATOS, "procesados")
CARPETA_REPORTES = os.path.join(DATOS, "reportes")
CARPETA_RUIDO = os.path.join(DATOS, "ruido")

# Cualquier carpeta que empiece por "impostor" (impostor_01, Impostor_ana...) es impostor: un nombre
# distinto de impostor_NN no debe convertirlo por error en integrante y meterlo al enrolamiento.
PATRON_IMPOSTOR = re.compile(r"^impostor", re.IGNORECASE)
PATRON_TOMA = re.compile(r"_([AB])_(\d+)\.wav$")

# Regla de descarte (aprobada): saturacion, corte dentro de la voz, perdida >= 300 ms sin corte ubicado
MARGEN_CORTE = 0.1             # s alrededor del tramo con voz
PERDIDA_MAXIMA_MS = 300

VENTANA_C = 3.0                # s: el habla libre del celular se corta en ventanas
VOZ_MINIMA_VENTANA = 1.5       # s de voz para usar una ventana

FRACCION_ENTRENAR = 0.7
CONDICIONES = ["ventilador", "carro", "murmullo", "todos", "ventilador_carro", "todos_murmullo"]
FRACCION_RUIDO_ENTRENAR = 0.6


def leer_wav(ruta):
    """WAV mono 16 kHz int16 -> array int16."""
    with wave.open(ruta) as w:
        if w.getnchannels() != 1 or w.getframerate() != h.TASA or w.getsampwidth() != 2:
            raise ValueError("{}: se espera mono 16 kHz int16".format(ruta))
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").copy()


def semilla_de(*partes):
    """Semilla estable (no depende de hash() de Python) a partir de textos y numeros."""
    return zlib.crc32("|".join(str(p) for p in partes).encode("utf-8"))


# ---------------- Personas ----------------
def personas():
    """(integrantes, impostores) segun las carpetas de datos_voz/inmp441/."""
    integrantes, impostores = [], []
    for d in sorted(os.listdir(CARPETA_INMP441)):
        if d.startswith("_") or not os.path.isdir(os.path.join(CARPETA_INMP441, d)):
            continue
        (impostores if PATRON_IMPOSTOR.match(d) else integrantes).append(d)
    return integrantes, impostores


# ---------------- INMP441 ----------------
def motivos_descarte(avisos, voz):
    """Lista de motivos graves (vacia = la toma sirve). voz = (inicio, fin) s o None."""
    motivos = []
    if "SATURACI" in avisos:
        motivos.append("saturación")
    if voz is None:
        motivos.append("sin voz")
    cortes = [float(t) for t in re.findall(r"posible corte en t = ([\d.]+) s", avisos)]
    if voz is not None:
        dentro = [t for t in cortes if voz[0] - MARGEN_CORTE <= t <= voz[1] + MARGEN_CORTE]
        if dentro:
            motivos.append("corte dentro de la voz (t = {})".format(", ".join("{:.2f}".format(t) for t in dentro)))
    perdida = sum(float(m) for m in re.findall(r"supera al audio en (\d+) ms", avisos))
    if perdida >= PERDIDA_MAXIMA_MS and not cortes:
        motivos.append("pérdida de {:.0f} ms".format(perdida))
    return motivos


def tomas_inmp441(persona, bloques=("A", "B")):
    """Tomas del INMP441 con 'usable' y 'motivo' segun la regla de descarte."""
    carpeta = os.path.join(CARPETA_INMP441, persona)
    avisos = {}
    ruta_csv = os.path.join(carpeta, "{}_grabaciones.csv".format(persona))
    if os.path.exists(ruta_csv):
        with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
            avisos = {fila["archivo"]: fila.get("huecos", "") for fila in csv.DictReader(f)}
    tomas = []
    for ruta in sorted(glob.glob(os.path.join(carpeta, "*.wav"))):
        nombre = os.path.basename(ruta)
        m = PATRON_TOMA.search(nombre)
        if not m or m.group(1) not in bloques:
            continue
        audio = leer_wav(ruta)
        motivos = motivos_descarte(avisos.get(nombre, ""), h.tramo_voz(audio))
        if not motivos and h.preparar(audio) is None:
            motivos.append("menos de {} s de voz".format(h.VOZ_MINIMA))
        tomas.append({"persona": persona, "bloque": m.group(1), "archivo": nombre, "ruta": ruta,
                      "fuente": "inmp441", "audio": audio, "usable": not motivos, "motivo": "; ".join(motivos)})
    return tomas


# ---------------- Celular ----------------
def tomas_celular(persona):
    """Segmentos del celular con uso=enrolar (A, B y ventanas de 3 s de C). [] si no hay."""
    ruta_csv = os.path.join(CARPETA_REPORTES, "segmentos_{}.csv".format(persona))
    if not os.path.exists(ruta_csv):
        return []
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        filas = [r for r in csv.DictReader(f) if r.get("uso") == "enrolar" and r.get("archivo")]
    tomas = []
    for fila in filas:
        nombre = fila["archivo"].replace(" (existente)", "")
        ruta = os.path.join(CARPETA_PROCESADOS, persona, nombre)
        if not os.path.exists(ruta):
            continue
        audio = leer_wav(ruta)
        if fila["bloque"] != "C":
            tomas.append({"persona": persona, "bloque": fila["bloque"], "archivo": nombre, "ruta": ruta,
                          "fuente": "celular", "audio": audio})
            continue
        paso = int(VENTANA_C * h.TASA)
        for k, ini in enumerate(range(0, len(audio) - paso + 1, paso)):
            ventana = audio[ini:ini + paso]
            mascara = h.tramos_con_voz(h.pasa_altos(h.a_flotante(ventana), fs=h.TASA))
            if mascara.sum() * h.TRAMO / h.TASA >= VOZ_MINIMA_VENTANA:
                tomas.append({"persona": persona, "bloque": "C", "archivo": "{}#{:02d}".format(nombre, k),
                              "ruta": ruta, "fuente": "celular", "audio": ventana})
    return tomas


# ---------------- Ruido ----------------
def condicion_de(nombre):
    """ruido_<lugar>_<condicion>_<nn>.wav -> condicion (la mas larga que coincida) o None."""
    base = re.sub(r"_\d+\.wav$", "", nombre)
    candidatas = [c for c in CONDICIONES if base.endswith("_" + c)]
    return max(candidatas, key=len) if candidatas else None


def ruidos():
    """{condicion: {'entrenar': float, 'prueba': float, 'archivos': [...]}} (sin 'base')."""
    por_condicion = {}
    for ruta in sorted(glob.glob(os.path.join(CARPETA_RUIDO, "*", "ruido_*.wav"))):
        c = condicion_de(os.path.basename(ruta))
        if c:
            por_condicion.setdefault(c, []).append(ruta)
    resultado = {}
    for c, rutas in por_condicion.items():
        audio = np.concatenate([h.a_flotante(leer_wav(r)) for r in rutas])
        corte = int(len(audio) * FRACCION_RUIDO_ENTRENAR)
        resultado[c] = {"entrenar": audio[:corte], "prueba": audio[corte:],
                        "archivos": [os.path.relpath(r, h.RAIZ) for r in rutas]}
    return resultado


def extracto(ruido, n, semilla):
    """n muestras de ruido desde una posicion elegida con la semilla (repite si es corto)."""
    if len(ruido) < n:
        ruido = np.tile(ruido, int(np.ceil(n / len(ruido))) + 1)
    ini = np.random.default_rng(semilla).integers(0, len(ruido) - n + 1)
    return ruido[ini:ini + n]


# ---------------- Division ----------------
def division(tomas, semilla, fraccion=FRACCION_ENTRENAR):
    """Archivos de entrenamiento: 70 % de las tomas usables de cada persona y bloque."""
    grupos = {}
    for t in tomas:
        if t["usable"]:
            grupos.setdefault((t["persona"], t["bloque"]), []).append(t["archivo"])
    entrenar = set()
    for clave, archivos in sorted(grupos.items()):
        archivos = sorted(archivos)
        orden = np.random.default_rng(semilla_de(semilla, *clave)).permutation(len(archivos))
        entrenar.update(archivos[i] for i in orden[:round(fraccion * len(archivos))])
    return entrenar
