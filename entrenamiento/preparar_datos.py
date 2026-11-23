"""
preparar_datos.py  -  CORRE EN EL PC
Une las frases de intenciones, las limpia y las reparte 80/20 (estratificado).

Fuentes:
  datos/sinteticas.csv   (plantillas de entrenamiento/generar_sinteticas.py)
  datos/generadas.csv    (frases propuestas y revisadas a mano por el grupo)
  datos/propias.csv      (opcional; no se usa en esta entrega)
  datos/massive/es-ES.jsonl  (MASSIVE, CC BY 4.0) con el mapeo aprobado:
    encender : iot_hue_lighton (sin verbo de apagar), iot_hue_lightup y iot_wemo_on
               (solo con verbo de encender), sin "no puedo encender las luces"
               (es un reclamo, no una orden)                    -> tope 100
    apagar   : iot_hue_lightoff e iot_wemo_off con verbo de apagar
               y sin "todo/todos/todas"                         -> tope 100
    saludo   : general_greet sin 3 frases que no son saludos
    fuera_de_dominio: 150 al azar de las intenciones que no son iot_* ni
               general_greet, sin verbos de encender/apagar
  En MASSIVE se quitan las palabras "olly", "alexa" y "siri".

Salida: datos/train.csv y datos/test.csv (texto normalizado, intencion, origen).

Ejecutar desde la carpeta del proyecto con:  py entrenamiento/preparar_datos.py
"""

import csv
import json
import os
import random
import re
import sys
from collections import Counter

from sklearn.model_selection import train_test_split

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar

DATOS = os.path.join(RAIZ, "datos")
SEMILLA = 42
TOPE_MASSIVE = {"encender": 100, "apagar": 100}
CANTIDAD_FUERA = 150

INTENCIONES = ["saludo", "encender", "apagar", "apagar_todo", "descansar",
               "consultar_estado", "agradecer", "fuera_de_dominio"]
PRIORIDAD = {"propia": 0, "generada": 1, "sintetica": 2, "massive": 3}   # ante duplicados gana la menor

# Filtros por verbo (sobre el texto original de MASSIVE, ya en minusculas)
ENCENDER = re.compile(r"\b(encend\w*|enciend\w*|prend\w*|activ\w*)")
APAGAR = re.compile(r"\b(apag\w*|desactiv\w*)")
TODO = re.compile(r"\b(todo|todos|todas)\b")
ASISTENTES = {"olly", "alexa", "siri"}
NO_SALUDOS = {"dime mis alarmas", "quien eres", "oye que es hoy"}
EXCLUIR_MASSIVE = {"no puedo encender las luces"}          # reclamo, no orden


# ---------------- Carga ----------------
def leer_csv(nombre, opcional=False):
    ruta = os.path.join(DATOS, nombre)
    if not os.path.exists(ruta):
        if not opcional:
            print("  AVISO: no existe datos/{}; sigo sin ese archivo.".format(nombre))
        return []
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f))
    print("  datos/{}: {} filas".format(nombre, len(filas)))
    return [{"texto": f.get("texto") or "", "intencion": (f.get("intencion") or "").strip(),
             "origen": (f.get("origen") or "").strip()} for f in filas]


def leer_massive():
    ruta = os.path.join(DATOS, "massive", "es-ES.jsonl")
    with open(ruta, encoding="utf-8") as f:
        filas = [json.loads(linea) for linea in f]
    print("  datos/massive/es-ES.jsonl: {} frases".format(len(filas)))
    azar = random.Random(SEMILLA)

    def de(intents):
        return [f["utt"].lower() for f in filas
                if f["intent"] in intents and normalizar(f["utt"]) not in EXCLUIR_MASSIVE]

    encender = [u for u in de({"iot_hue_lighton"}) if not APAGAR.search(u)]
    encender += [u for u in de({"iot_hue_lightup", "iot_wemo_on"})
                 if ENCENDER.search(u) and not APAGAR.search(u)]
    apagar = [u for u in de({"iot_hue_lightoff", "iot_wemo_off"})
              if APAGAR.search(u) and not ENCENDER.search(u) and not TODO.search(u)]
    saludo = [u for u in de({"general_greet"}) if normalizar(u) not in NO_SALUDOS]
    otras = [f["utt"].lower() for f in filas
             if not f["intent"].startswith("iot_") and f["intent"] != "general_greet"
             and not ENCENDER.search(f["utt"].lower()) and not APAGAR.search(f["utt"].lower())]

    print("  MASSIVE antes de topes: encender {}, apagar {}, saludo {}, candidatas fuera {}".format(
        len(encender), len(apagar), len(saludo), len(otras)))

    def recortar(lista, tope):
        return azar.sample(lista, tope) if len(lista) > tope else lista

    grupos = {
        "encender": recortar(encender, TOPE_MASSIVE["encender"]),
        "apagar": recortar(apagar, TOPE_MASSIVE["apagar"]),
        "saludo": saludo,
        "fuera_de_dominio": recortar(otras, CANTIDAD_FUERA),
    }
    return [{"texto": u, "intencion": intencion, "origen": "massive"}
            for intencion, utts in grupos.items() for u in utts]


def quitar_asistentes(texto):
    return " ".join(p for p in texto.split() if p not in ASISTENTES)


# ---------------- Limpieza ----------------
def limpiar(filas):
    invalidas = 0
    vistas = {}          # texto normalizado -> fila elegida
    intenciones_por_texto = {}
    for fila in filas:
        texto = normalizar(fila["texto"])
        if fila["origen"] == "massive":
            texto = quitar_asistentes(texto)
        if not texto or fila["intencion"] not in INTENCIONES or fila["origen"] not in PRIORIDAD:
            invalidas += 1
            continue
        nueva = {"texto": texto, "intencion": fila["intencion"], "origen": fila["origen"]}
        intenciones_por_texto.setdefault(texto, set()).add(nueva["intencion"])
        actual = vistas.get(texto)
        if actual is None or PRIORIDAD[nueva["origen"]] < PRIORIDAD[actual["origen"]]:
            vistas[texto] = nueva

    conflictos = {t: i for t, i in intenciones_por_texto.items() if len(i) > 1}
    print("\nLimpieza: {} filas invalidas o vacias, {} duplicados eliminados, {} conflictos".format(
        invalidas, len(filas) - invalidas - len(vistas), len(conflictos)))
    for texto, intenciones in sorted(conflictos.items()):
        print("  CONFLICTO '{}' {} -> se queda '{}' ({})".format(
            texto, sorted(intenciones), vistas[texto]["intencion"], vistas[texto]["origen"]))
    return list(vistas.values())


def leer_demo():
    """Textos normalizados de datos/frases_demo.txt (formato texto;intencion)."""
    ruta = os.path.join(DATOS, "frases_demo.txt")
    if not os.path.exists(ruta):
        print("\nAVISO: no existe datos/frases_demo.txt")
        return set()
    with open(ruta, encoding="utf-8") as f:
        return {normalizar(linea.rsplit(";", 1)[0]) for linea in f if ";" in linea}


def quitar_demo(filas):
    """Descarta del dataset cualquier frase de la demo, venga del origen que venga."""
    demo = leer_demo()
    for f in filas:
        if f["texto"] in demo:
            print("  DESCARTADA (es de la demo): '{}' ({}, {})".format(
                f["texto"], f["intencion"], f["origen"]))
    filas = [f for f in filas if f["texto"] not in demo]
    copiadas = sum(1 for f in filas if f["texto"] in demo)
    print("\nFrases de la demo en el dataset despues del filtro: {}".format(copiadas))
    if copiadas:
        print("  ADVERTENCIA: quedaron frases de la demo en el dataset")
    return filas


def guardar(filas, nombre):
    with open(os.path.join(DATOS, nombre), "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=["texto", "intencion", "origen"])
        escritor.writeheader()
        escritor.writerows(filas)


# ---------------- Programa principal ----------------
print("Cargando fuentes...")
filas = (leer_csv("propias.csv", opcional=True) + leer_csv("sinteticas.csv")
         + leer_csv("generadas.csv") + leer_massive())
filas = limpiar(filas)
filas = quitar_demo(filas)

etiquetas = [f["intencion"] for f in filas]
train, test = train_test_split(filas, test_size=0.2, stratify=etiquetas, random_state=SEMILLA)
guardar(train, "train.csv")
guardar(test, "test.csv")

# ---------------- Reporte ----------------
origenes = ["massive", "sintetica", "generada"]
por_origen = Counter((f["intencion"], f["origen"]) for f in filas)
n_train = Counter(f["intencion"] for f in train)
n_test = Counter(f["intencion"] for f in test)

print("\nConteo final por intencion y origen:")
print("  {:18} {:>7} {:>9} {:>8} {:>6} {:>6} {:>5}".format(
    "intencion", *origenes, "total", "train", "test"))
for intencion in INTENCIONES:
    total = sum(por_origen[(intencion, o)] for o in origenes)
    print("  {:18} {:7d} {:9d} {:8d} {:6d} {:6d} {:5d}".format(
        intencion, *[por_origen[(intencion, o)] for o in origenes],
        total, n_train[intencion], n_test[intencion]))
print("  {:18} {:7d} {:9d} {:8d} {:6d} {:6d} {:5d}".format(
    "TOTAL", *[sum(v for (i, o), v in por_origen.items() if o == org) for org in origenes],
    len(filas), len(train), len(test)))

azar = random.Random(SEMILLA)
print("\n5 ejemplos por intencion (texto normalizado, origen):")
for intencion in INTENCIONES:
    grupo = [f for f in filas if f["intencion"] == intencion]
    print("  {}:".format(intencion))
    for f in azar.sample(grupo, min(5, len(grupo))):
        print("     - {:45} ({})".format(f["texto"], f["origen"]))

print("\nGuardados datos/train.csv ({}) y datos/test.csv ({}).".format(len(train), len(test)))
