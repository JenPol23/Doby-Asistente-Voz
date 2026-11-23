"""
entrenar_base.py  -  CORRE EN EL PC
Modelo base de intenciones: TF-IDF (palabras 1-2 + caracteres 2-5) + LogisticRegression
con class_weight="balanced". Entrena SOLO con datos/train.csv y evalua con datos/test.csv.

Guarda:
  modelos/base.joblib                    (pipeline completo: vectorizadores + clasificador)
  modelos/base_info.json                 (intenciones, fecha, tamanos y metricas)
  resultados/base_metricas.txt           (reporte completo)
  resultados/base_matriz_confusion.csv   (matriz de confusion)
  resultados/base_matriz_confusion.png   (solo si matplotlib esta instalado)

Ejecutar desde la carpeta del proyecto con:  py entrenamiento/entrenar_base.py
Candidato (NO toca modelos/base.joblib):     py entrenamiento/entrenar_base.py --candidato NOMBRE
  -> modelos/NOMBRE/ y resultados/NOMBRE/ con los mismos archivos; se aprueba copiandolo a mano.
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter
from datetime import datetime

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import FeatureUnion, Pipeline

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar

DATOS = os.path.join(RAIZ, "datos")
MODELOS = os.path.join(RAIZ, "modelos")
RESULTADOS = os.path.join(RAIZ, "resultados")
SEMILLA = 42
MAX_FALLOS = 30

parser = argparse.ArgumentParser(description="Entrena el modelo base de intenciones")
parser.add_argument("--candidato", metavar="NOMBRE",
                    help="guardar en modelos/NOMBRE/ y resultados/NOMBRE/ (no reemplaza modelos/base.joblib)")
args = parser.parse_args()
if args.candidato:
    MODELOS = os.path.join(MODELOS, args.candidato)
    RESULTADOS = os.path.join(RESULTADOS, args.candidato)
    os.makedirs(MODELOS, exist_ok=True)
    os.makedirs(RESULTADOS, exist_ok=True)

INTENCIONES = ["saludo", "encender", "apagar", "apagar_todo", "descansar",
               "consultar_estado", "agradecer", "fuera_de_dominio"]
ORIGENES = ["massive", "sintetica", "generada"]

lineas = []          # todo lo que se imprime tambien va a base_metricas.txt


def salida(texto=""):
    print(texto)
    lineas.append(texto)


def leer_csv(nombre):
    with open(os.path.join(DATOS, nombre), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def leer_demo():
    """Lista de (frase original, intencion esperada) de datos/frases_demo.txt."""
    with open(os.path.join(DATOS, "frases_demo.txt"), encoding="utf-8") as f:
        return [tuple(p.strip() for p in linea.rsplit(";", 1)) for linea in f if ";" in linea]


def crear_modelo():
    caracteristicas = FeatureUnion([
        ("palabras", TfidfVectorizer(analyzer="word", ngram_range=(1, 2))),
        ("caracteres", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5))),
    ])
    clasificador = LogisticRegression(class_weight="balanced", max_iter=2000,
                                      random_state=SEMILLA)
    return Pipeline([("tfidf", caracteristicas), ("clasificador", clasificador)])


def predecir(modelo, textos):
    """Devuelve (intenciones, confianzas) para textos ya normalizados."""
    probabilidades = modelo.predict_proba(textos)
    clases = modelo.classes_
    indices = probabilidades.argmax(axis=1)
    return [clases[i] for i in indices], probabilidades.max(axis=1)


def guardar_imagen(matriz, ruta):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        salida("matplotlib no esta instalado: sigo sin la imagen.")
        return False
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.imshow(matriz, cmap="Blues")
    ax.set_xticks(range(len(INTENCIONES)), INTENCIONES, rotation=45, ha="right")
    ax.set_yticks(range(len(INTENCIONES)), INTENCIONES)
    ax.set_xlabel("Prediccion")
    ax.set_ylabel("Intencion real")
    ax.set_title("Modelo base (TF-IDF + LogisticRegression): matriz de confusion en test")
    limite = matriz.max() / 2
    for i in range(len(INTENCIONES)):
        for j in range(len(INTENCIONES)):
            ax.text(j, i, str(matriz[i, j]), ha="center", va="center",
                    color="white" if matriz[i, j] > limite else "black")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return True


# ---------------- Datos ----------------
train = leer_csv("train.csv")
test = leer_csv("test.csv")
x_train = [f["texto"] for f in train]
y_train = [f["intencion"] for f in train]
x_test = [f["texto"] for f in test]
y_test = [f["intencion"] for f in test]
salida("Datos: train {} frases, test {} frases".format(len(train), len(test)))

# ---------------- Entrenamiento ----------------
modelo = crear_modelo()
modelo.fit(x_train, y_train)
salida("Modelo entrenado. Caracteristicas TF-IDF: {}".format(
    len(modelo.named_steps["tfidf"].get_feature_names_out())))

# ---------------- Evaluacion en test ----------------
pred_test, conf_test = predecir(modelo, x_test)
accuracy = accuracy_score(y_test, pred_test)
f1_macro = f1_score(y_test, pred_test, average="macro")
salida("\n=== TEST ===")
salida("Accuracy: {:.4f}".format(accuracy))
salida("F1 macro: {:.4f}".format(f1_macro))
salida("\nReporte por clase:")
salida(classification_report(y_test, pred_test, labels=INTENCIONES, digits=3, zero_division=0))

# Matriz de confusion (filas = real, columnas = prediccion)
matriz = confusion_matrix(y_test, pred_test, labels=INTENCIONES)
salida("Matriz de confusion (filas = real, columnas = prediccion):")
salida("  {:18} ".format("") + " ".join("{:>4}".format(i) for i in range(len(INTENCIONES))))
for i, intencion in enumerate(INTENCIONES):
    salida("  {:>2} {:15} ".format(i, intencion) + " ".join("{:4d}".format(v) for v in matriz[i]))
with open(os.path.join(RESULTADOS, "base_matriz_confusion.csv"), "w", encoding="utf-8", newline="") as f:
    escritor = csv.writer(f)
    escritor.writerow(["real \\ prediccion"] + INTENCIONES)
    for intencion, fila in zip(INTENCIONES, matriz):
        escritor.writerow([intencion] + [int(v) for v in fila])

# Acierto por origen
salida("\nAcierto por origen (test):")
acierto_origen = {}
for origen in ORIGENES:
    idx = [i for i, f in enumerate(test) if f["origen"] == origen]
    buenos = sum(1 for i in idx if pred_test[i] == y_test[i])
    acierto_origen[origen] = {"aciertos": buenos, "total": len(idx),
                              "acierto": round(buenos / len(idx), 4) if idx else None}
    salida("  {:10} {:3d}/{:3d} = {:.4f}".format(origen, buenos, len(idx),
                                                  buenos / len(idx) if idx else 0))

# Frases de test falladas
fallos = [(x_test[i], y_test[i], pred_test[i], conf_test[i])
          for i in range(len(test)) if pred_test[i] != y_test[i]]
salida("\nFrases de test falladas: {} (se muestran maximo {})".format(len(fallos), MAX_FALLOS))
for texto, real, pred, conf in fallos[:MAX_FALLOS]:
    salida("  '{}'  real={}  pred={}  conf={:.2f}".format(texto, real, pred, conf))

# ---------------- Frases de la demo ----------------
demo = leer_demo()
pred_demo, conf_demo = predecir(modelo, [normalizar(frase) for frase, _ in demo])
aciertos_demo = 0
salida("\n=== FRASES DE LA DEMO ({}) ===".format(len(demo)))
salida("  {:2} {:45} {:17} {:17} {:>5}  {}".format("#", "frase", "esperada", "prediccion", "conf", "ok"))
for n, ((frase, esperada), pred, conf) in enumerate(zip(demo, pred_demo, conf_demo), 1):
    ok = pred == esperada
    aciertos_demo += ok
    aviso = "  (conf < 0.5 -> 'no te entendi')" if conf < 0.5 else ""
    salida("  {:2d} {:45} {:17} {:17} {:5.2f}  {}{}".format(
        n, frase, esperada, pred, conf, "SI" if ok else "NO", aviso))
salida("Acierto demo: {}/{} = {:.4f}".format(aciertos_demo, len(demo), aciertos_demo / len(demo)))

# ---------------- Guardado ----------------
if guardar_imagen(matriz, os.path.join(RESULTADOS, "base_matriz_confusion.png")):
    salida("\nImagen: {}".format(os.path.relpath(os.path.join(RESULTADOS, "base_matriz_confusion.png"), RAIZ)))

joblib.dump(modelo, os.path.join(MODELOS, "base.joblib"))
info = {
    "modelo": "TF-IDF (palabras 1-2 + caracteres char_wb 2-5) + LogisticRegression(class_weight=balanced)",
    "intenciones": list(modelo.classes_),
    "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "dataset": {"train": len(train), "test": len(test),
                "train_por_intencion": dict(Counter(y_train))},
    "metricas_test": {"accuracy": round(accuracy, 4), "f1_macro": round(f1_macro, 4),
                      "por_origen": acierto_origen},
    "demo": {"aciertos": aciertos_demo, "total": len(demo),
             "acierto": round(aciertos_demo / len(demo), 4)},
}
with open(os.path.join(MODELOS, "base_info.json"), "w", encoding="utf-8") as f:
    json.dump(info, f, ensure_ascii=False, indent=2)
salida("Guardados {}/base.joblib y base_info.json".format(os.path.relpath(MODELOS, RAIZ)))

with open(os.path.join(RESULTADOS, "base_metricas.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lineas) + "\n")
print("Guardados {0}/base_metricas.txt y {0}/base_matriz_confusion.csv".format(os.path.relpath(RESULTADOS, RAIZ)))
