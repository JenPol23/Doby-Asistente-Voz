"""
matriz_confusion_modelo.py  -  CORRE EN EL PC
Matriz de confusion de un modelo de intenciones guardado, sobre un test.csv, con el mismo formato que
entrenamiento/entrenar_base.py (CSV con filas = real, columnas = prediccion, y PNG). Sirve para tener en el
informe la matriz del modelo anterior (desde respaldos/) junto a la del modelo nuevo.

Uso:
  py entrenamiento/matriz_confusion_modelo.py --modelo M.joblib --test T.csv --salida resultados/NOMBRE [--titulo "..."]
  -> resultados/NOMBRE.csv y resultados/NOMBRE.png
"""

import argparse
import csv
import os

import joblib
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

INTENCIONES = ["saludo", "encender", "apagar", "apagar_todo", "descansar",
               "consultar_estado", "agradecer", "fuera_de_dominio"]      # mismo orden que entrenar_base.py


def guardar_imagen(matriz, ruta, titulo):
    """Igual que entrenar_base.guardar_imagen(), con el titulo como parametro."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.imshow(matriz, cmap="Blues")
    ax.set_xticks(range(len(INTENCIONES)), INTENCIONES, rotation=45, ha="right")
    ax.set_yticks(range(len(INTENCIONES)), INTENCIONES)
    ax.set_xlabel("Prediccion")
    ax.set_ylabel("Intencion real")
    ax.set_title(titulo)
    limite = matriz.max() / 2
    for i in range(len(INTENCIONES)):
        for j in range(len(INTENCIONES)):
            ax.text(j, i, str(matriz[i, j]), ha="center", va="center",
                    color="white" if matriz[i, j] > limite else "black")
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Matriz de confusion de un modelo guardado")
    parser.add_argument("--modelo", required=True)
    parser.add_argument("--test", required=True, help="test.csv ya normalizado (texto, intencion)")
    parser.add_argument("--salida", required=True, help="ruta sin extension: se escriben .csv y .png")
    parser.add_argument("--titulo", default="Modelo base (TF-IDF + LogisticRegression): matriz de confusion en test")
    args = parser.parse_args()

    with open(args.test, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    x, y = [f["texto"] for f in filas], [f["intencion"] for f in filas]
    pred = joblib.load(args.modelo).predict(x)
    matriz = confusion_matrix(y, pred, labels=INTENCIONES)
    print("{} frases: accuracy {:.4f}, F1 macro {:.4f}".format(
        len(x), accuracy_score(y, pred), f1_score(y, pred, average="macro")))

    with open(args.salida + ".csv", "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["real \\ prediccion"] + INTENCIONES)
        for intencion, fila in zip(INTENCIONES, matriz):
            escritor.writerow([intencion] + [int(v) for v in fila])
    guardar_imagen(matriz, args.salida + ".png", args.titulo)
    print("Guardados {0}.csv y {0}.png".format(args.salida))


if __name__ == "__main__":
    main()
