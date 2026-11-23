"""
graficas.py  -  CORRE EN EL PC
Graficas para la sustentacion, en resultados/graficas/ (PNG, 150 dpi).

Solo LEE: modelos/base.joblib, datos/train.csv, datos/test.csv,
datos/frases_demo.txt y resultados/comparacion_datos.txt (datos del "antes").
La curva de aprendizaje entrena modelos temporales en memoria (misma
configuracion que entrenar_base.py) y no guarda ningun modelo.

Ejecutar desde la carpeta del proyecto con:  py entrenamiento/graficas.py
"""

import csv
import os
import re
import sys
from collections import Counter

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_recall_fscore_support)
from sklearn.model_selection import StratifiedKFold, learning_curve
from sklearn.pipeline import FeatureUnion, Pipeline

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar

DATOS = os.path.join(RAIZ, "datos")
RESULTADOS = os.path.join(RAIZ, "resultados")
CARPETA = os.path.join(RESULTADOS, "graficas")
SEMILLA = 42
UMBRAL = 0.5
DPI = 150

INTENCIONES = ["saludo", "encender", "apagar", "apagar_todo", "descansar",
               "consultar_estado", "agradecer", "fuera_de_dominio"]
ORIGENES = ["massive", "sintetica", "generada"]
COLOR_ORIGEN = {"massive": "#4C72B0", "sintetica": "#55A868", "generada": "#DD8452"}
COLOR_ANTES = "#A0A0A0"
COLOR_DESPUES = "#4C72B0"
COLOR_ERROR = "#C44E52"
NOTA_TEST = "Antes y despues se evaluaron cada uno con su propio test.csv (223 frases); la demo es la misma."


# ---------------- Lectura ----------------
def leer_csv(nombre):
    with open(os.path.join(DATOS, nombre), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_demo():
    """Lista de (frase original, intencion esperada) de datos/frases_demo.txt."""
    with open(os.path.join(DATOS, "frases_demo.txt"), encoding="utf-8") as f:
        return [tuple(p.strip() for p in linea.rsplit(";", 1)) for linea in f if ";" in linea]


def leer_comparacion():
    """Lee de comparacion_datos.txt las metricas y la demo de 'antes' y 'despues'."""
    with open(os.path.join(RESULTADOS, "comparacion_datos.txt"), encoding="utf-8") as f:
        lineas = f.read().splitlines()
    metricas = {}
    demo = []
    for linea in lineas:
        m = re.match(r"^(Accuracy test|F1 macro test)\s+([\d.]+)\s+([\d.]+)\s*$", linea)
        if m:
            metricas[m.group(1)] = (float(m.group(2)), float(m.group(3)))
            continue
        m = re.match(r"^Acierto (\w+)\s+(\d+)/(\d+)\s+(\d+)/(\d+)\s*$", linea)
        if m:
            metricas[m.group(1)] = ((int(m.group(2)), int(m.group(3))),
                                    (int(m.group(4)), int(m.group(5))))
            continue
        # Filas de la demo: " n frase ... esperada | pred conf SI | pred conf SI"
        partes = linea.split("|")
        if len(partes) == 3 and re.match(r"^\s*\d+ ", partes[0]):
            izquierda = partes[0].split()
            antes = partes[1].split()
            despues = partes[2].split()
            demo.append({"n": int(izquierda[0]), "frase": " ".join(izquierda[1:-1]),
                         "esperada": izquierda[-1],
                         "antes": (antes[0], float(antes[1]), antes[2] == "SI"),
                         "despues": (despues[0], float(despues[1]), despues[2] == "SI")})
    faltan = [c for c in ("Accuracy test", "F1 macro test", "massive", "sintetica",
                          "generada", "demo") if c not in metricas]
    if faltan or len(demo) != 22:
        sys.exit("ERROR: faltan datos del 'antes' en comparacion_datos.txt: {} (demo: {} filas)".format(
            faltan, len(demo)))
    return metricas, demo


def crear_modelo():
    """Misma configuracion que entrenamiento/entrenar_base.py (copiada: ese script
    no se puede importar porque al importarlo reentrena y guarda base.joblib)."""
    caracteristicas = FeatureUnion([
        ("palabras", TfidfVectorizer(analyzer="word", ngram_range=(1, 2))),
        ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5))),
    ])
    clasificador = LogisticRegression(class_weight="balanced", max_iter=2000,
                                      random_state=SEMILLA)
    return Pipeline([("tfidf", caracteristicas), ("clasificador", clasificador)])


def guardar(fig, nombre):
    ruta = os.path.join(CARPETA, nombre)
    fig.tight_layout()
    fig.savefig(ruta, dpi=DPI)
    plt.close(fig)
    print("  Guardada: resultados/graficas/{}".format(nombre))


def etiquetas_barras(ax, barras, textos):
    for barra, texto in zip(barras, textos):
        ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + 0.004, texto,
                ha="center", va="bottom", fontsize=8)


# ---------------- Datos ----------------
os.makedirs(CARPETA, exist_ok=True)
train = leer_csv("train.csv")
test = leer_csv("test.csv")
demo_frases = leer_demo()
comparacion, demo_comp = leer_comparacion()

modelo = joblib.load(os.path.join(RAIZ, "modelos", "base.joblib"))   # solo lectura


def predecir(textos):
    probabilidades = modelo.predict_proba(textos)
    return list(modelo.classes_[probabilidades.argmax(axis=1)]), probabilidades.max(axis=1)


x_test = [f["texto"] for f in test]
y_test = [f["intencion"] for f in test]
pred_test, conf_test = predecir(x_test)
pred_demo, conf_demo = predecir([normalizar(frase) for frase, _ in demo_frases])

acc = accuracy_score(y_test, pred_test)
f1m = f1_score(y_test, pred_test, average="macro")
aciertos_demo = sum(p == e for p, (_, e) in zip(pred_demo, demo_frases))
origen_despues = {}
for origen in ORIGENES:
    idx = [i for i, f in enumerate(test) if f["origen"] == origen]
    origen_despues[origen] = (sum(pred_test[i] == y_test[i] for i in idx), len(idx))

# ---------------- Verificacion contra comparacion_datos.txt ----------------
print("Verificacion del modelo guardado contra la columna 'despues' de comparacion_datos.txt:")
chequeos = [
    ("Accuracy", round(acc, 4), comparacion["Accuracy test"][1]),
    ("F1 macro", round(f1m, 4), comparacion["F1 macro test"][1]),
    ("Demo", (aciertos_demo, len(demo_frases)), comparacion["demo"][1]),
] + [(o, origen_despues[o], comparacion[o][1]) for o in ORIGENES]
todo_ok = True
for nombre, calculado, archivo in chequeos:
    ok = calculado == tuple(archivo) if isinstance(archivo, tuple) else calculado == archivo
    todo_ok &= ok
    print("  {:10} calculado {}   archivo {}   {}".format(nombre, calculado, archivo, "OK" if ok else "NO COINCIDE"))
for fila, (frase, esperada), pred, conf in zip(demo_comp, demo_frases, pred_demo, conf_demo):
    if fila["esperada"] != esperada or fila["despues"][0] != pred or abs(fila["despues"][1] - conf) > 0.0015:
        todo_ok = False
        print("  NO COINCIDE la frase de la demo {}: '{}'".format(fila["n"], frase))
print("  -> {}".format("todo coincide" if todo_ok else "AVISO: hay diferencias, revisar"))

print("\nGraficas:")

# ---------------- 1. Frases por intencion y origen ----------------
conteo = Counter((f["intencion"], f["origen"]) for f in train + test)
fig, ax = plt.subplots(figsize=(10, 5.5))
base = np.zeros(len(INTENCIONES))
for origen in ORIGENES:
    valores = np.array([conteo[(i, origen)] for i in INTENCIONES])
    ax.bar(INTENCIONES, valores, bottom=base, label=origen, color=COLOR_ORIGEN[origen])
    base += valores
for x, total in enumerate(base):
    ax.text(x, total + 3, str(int(total)), ha="center", fontsize=9)
ax.set_title("Frases por intención y origen (train + test = {} frases)".format(len(train) + len(test)))
ax.set_xlabel("Intención")
ax.set_ylabel("Número de frases")
ax.tick_params(axis="x", rotation=30)
ax.legend(title="Origen")
guardar(fig, "01_frases_por_intencion.png")

# ---------------- 2. Antes vs despues: metricas ----------------
nombres = ["Accuracy (test)", "F1 macro (test)", "Acierto demo"]
d_antes, d_despues = comparacion["demo"]
antes = [comparacion["Accuracy test"][0], comparacion["F1 macro test"][0], d_antes[0] / d_antes[1]]
despues = [acc, f1m, aciertos_demo / len(demo_frases)]
x = np.arange(len(nombres))
fig, ax = plt.subplots(figsize=(8, 5))
b1 = ax.bar(x - 0.2, antes, 0.4, label="Antes", color=COLOR_ANTES)
b2 = ax.bar(x + 0.2, despues, 0.4, label="Después", color=COLOR_DESPUES)
etiquetas_barras(ax, b1, ["{:.3f}".format(v) for v in antes])
etiquetas_barras(ax, b2, ["{:.3f}".format(v) for v in despues])
ax.set_xticks(x, nombres)
ax.set_ylim(0.8, 1.03)
ax.set_ylabel("Valor (el eje empieza en 0.8)")
ax.set_title("Modelo base antes y después de mejorar los datos")
ax.legend(loc="lower right")
fig.text(0.5, 0.01, NOTA_TEST, ha="center", fontsize=7)
fig.subplots_adjust(bottom=0.12)
guardar(fig, "02_antes_despues_metricas.png")

# ---------------- 3. Acierto por origen ----------------
x = np.arange(len(ORIGENES))
antes_o = [comparacion[o][0] for o in ORIGENES]
despues_o = [origen_despues[o] for o in ORIGENES]
fig, ax = plt.subplots(figsize=(8, 5))
b1 = ax.bar(x - 0.2, [a / n for a, n in antes_o], 0.4, label="Antes", color=COLOR_ANTES)
b2 = ax.bar(x + 0.2, [a / n for a, n in despues_o], 0.4, label="Después", color=COLOR_DESPUES)
etiquetas_barras(ax, b1, ["{}/{}".format(a, n) for a, n in antes_o])
etiquetas_barras(ax, b2, ["{}/{}".format(a, n) for a, n in despues_o])
ax.set_xticks(x, ["MASSIVE", "Sintéticas", "Generadas"])
ax.set_ylim(0.8, 1.03)
ax.set_ylabel("Acierto en test (el eje empieza en 0.8)")
ax.set_xlabel("Origen de la frase")
ax.set_title("Acierto por origen de los datos, antes y después")
ax.legend(loc="lower right")
fig.text(0.5, 0.01, NOTA_TEST, ha="center", fontsize=7)
guardar(fig, "03_acierto_por_origen.png")

# ---------------- 4. Confianza en la demo ----------------
n = len(demo_comp)
y = np.arange(n)[::-1]                        # frase 1 arriba
conf_antes = [f["antes"][1] for f in demo_comp]
ok_antes = [f["antes"][2] for f in demo_comp]
ok_despues = [p == e for p, (_, e) in zip(pred_demo, demo_frases)]
fig, ax = plt.subplots(figsize=(10, 10))
ax.barh(y + 0.2, conf_antes, 0.4, color=[COLOR_ANTES if ok else COLOR_ERROR for ok in ok_antes])
ax.barh(y - 0.2, conf_demo, 0.4, color=[COLOR_DESPUES if ok else COLOR_ERROR for ok in ok_despues])
for yi, (c, ok) in zip(y + 0.2, zip(conf_antes, ok_antes)):
    ax.text(c + 0.01, yi, "{:.2f}{}".format(c, "" if ok else "  FALLÓ"), va="center", fontsize=7)
for yi, (c, ok) in zip(y - 0.2, zip(conf_demo, ok_despues)):
    ax.text(c + 0.01, yi, "{:.2f}{}".format(c, "" if ok else "  FALLÓ"), va="center", fontsize=7)
ax.axvline(UMBRAL, color="black", linestyle="--", linewidth=1)
ax.text(UMBRAL + 0.005, n - 0.4, "umbral 0.5", fontsize=8)
ax.set_yticks(y, ["{:2d}. {}".format(f["n"], frase) for f, (frase, _) in zip(demo_comp, demo_frases)],
              fontsize=8)
ax.set_xlim(0, 1.1)
ax.set_xlabel("Confianza del modelo en la intención predicha")
ax.set_title("Confianza en las 22 frases de la demo, antes y después")
ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=COLOR_ANTES),
                   plt.Rectangle((0, 0), 1, 1, color=COLOR_DESPUES),
                   plt.Rectangle((0, 0), 1, 1, color=COLOR_ERROR)],
          labels=["Antes (acertó)", "Después (acertó)", "Falló"], loc="lower right")
guardar(fig, "04_confianza_demo.png")

# ---------------- 5. Precision, recall y F1 por intencion ----------------
precision, recall, f1, soporte = precision_recall_fscore_support(
    y_test, pred_test, labels=INTENCIONES, zero_division=0)
x = np.arange(len(INTENCIONES))
fig, ax = plt.subplots(figsize=(11, 5.5))
ax.bar(x - 0.27, precision, 0.27, label="Precisión", color="#4C72B0")
ax.bar(x, recall, 0.27, label="Recall", color="#55A868")
ax.bar(x + 0.27, f1, 0.27, label="F1", color="#DD8452")
ax.set_xticks(x, ["{}\n(n={})".format(i, s) for i, s in zip(INTENCIONES, soporte)], fontsize=8)
ax.set_ylim(0.8, 1.03)
ax.set_ylabel("Valor (el eje empieza en 0.8)")
ax.set_title("Precisión, recall y F1 por intención (modelo final, test)")
ax.legend(loc="lower right")
guardar(fig, "05_metricas_por_intencion.png")

# ---------------- 6. Matriz de confusion en porcentajes ----------------
matriz = confusion_matrix(y_test, pred_test, labels=INTENCIONES, normalize="true") * 100
fig, ax = plt.subplots(figsize=(8.5, 7.5))
imagen = ax.imshow(matriz, cmap="Blues", vmin=0, vmax=100)
fig.colorbar(imagen, ax=ax, label="% de las frases de cada intención real")
ax.set_xticks(range(len(INTENCIONES)), INTENCIONES, rotation=45, ha="right")
ax.set_yticks(range(len(INTENCIONES)), INTENCIONES)
ax.set_xlabel("Intención predicha")
ax.set_ylabel("Intención real")
ax.set_title("Matriz de confusión en porcentajes (modelo final, test)")
for i in range(len(INTENCIONES)):
    for j in range(len(INTENCIONES)):
        if matriz[i, j] > 0:
            ax.text(j, i, "{:.0f}%".format(matriz[i, j]), ha="center", va="center", fontsize=8,
                    color="white" if matriz[i, j] > 50 else "black")
guardar(fig, "06_matriz_confusion_pct.png")

# ---------------- 7. Curva de aprendizaje ----------------
print("  Curva de aprendizaje: entrenando modelos temporales (5 pliegues x 10 tamanos)...")
x_train = [f["texto"] for f in train]
y_train = [f["intencion"] for f in train]
porcentajes = np.linspace(0.1, 1.0, 10)
tamanos, f1_entreno, f1_valid = learning_curve(
    crear_modelo(), x_train, y_train, train_sizes=porcentajes,
    cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=SEMILLA),
    scoring="f1_macro", shuffle=True, random_state=SEMILLA)
fig, ax = plt.subplots(figsize=(8, 5))
for valores, nombre, color in ((f1_entreno, "Entrenamiento", "#55A868"),
                               (f1_valid, "Validación cruzada", "#4C72B0")):
    media, desv = valores.mean(axis=1), valores.std(axis=1)
    ax.plot(porcentajes * 100, media, "o-", label=nombre, color=color)
    ax.fill_between(porcentajes * 100, media - desv, media + desv, alpha=0.2, color=color)
ax.set_xlabel("% de los datos de entrenamiento ({} a {} frases por pliegue)".format(tamanos[0], tamanos[-1]))
ax.set_ylabel("F1 macro")
ax.set_title("Curva de aprendizaje (validación cruzada estratificada, 5 pliegues)")
ax.set_xticks(porcentajes * 100)
ax.grid(alpha=0.3)
ax.legend(loc="lower right")
guardar(fig, "07_curva_aprendizaje.png")

# ---------------- 8. Histograma de confianza ----------------
aciertos = np.array([p == r for p, r in zip(pred_test, y_test)])
bordes = np.linspace(0, 1, 21)
fig, ax = plt.subplots(figsize=(8, 5))
ax.hist(conf_test[aciertos], bins=bordes, color=COLOR_DESPUES, alpha=0.8,
        label="Aciertos ({})".format(int(aciertos.sum())))
ax.hist(conf_test[~aciertos], bins=bordes, color=COLOR_ERROR, alpha=0.9,
        label="Errores ({})".format(int((~aciertos).sum())))
ax.axvline(UMBRAL, color="black", linestyle="--", linewidth=1, label="Umbral 0.5")
ax.set_xlabel("Confianza del modelo")
ax.set_ylabel("Número de frases de test")
ax.set_title("Confianza en test: aciertos y errores (modelo final)")
ax.legend()
guardar(fig, "08_histograma_confianza.png")

# ---------------- Resumen por consola ----------------
print("\nResumen (modelo final, test de {} frases):".format(len(test)))
print("  Accuracy {:.4f}   F1 macro {:.4f}   Demo {}/{}".format(acc, f1m, aciertos_demo, len(demo_frases)))
for i, p, r, f, s in zip(INTENCIONES, precision, recall, f1, soporte):
    print("  {:17} precision {:.3f}  recall {:.3f}  F1 {:.3f}  (n={})".format(i, p, r, f, s))
print("  Curva de aprendizaje (F1 macro de validacion, media):")
print("   " + "  ".join("{:.0f}%={:.3f}".format(p * 100, v) for p, v in zip(porcentajes, f1_valid.mean(axis=1))))
print("  Test bajo el umbral 0.5: {} aciertos y {} errores".format(
    int(((conf_test < UMBRAL) & aciertos).sum()), int(((conf_test < UMBRAL) & ~aciertos).sum())))
print("  Errores en test:")
for i in np.where(~aciertos)[0]:
    print("   '{}'  real={}  pred={}  conf={:.2f}".format(x_test[i], y_test[i], pred_test[i], conf_test[i]))
