"""
probar_modelo.py  -  CORRE EN EL PC
Carga el modelo GUARDADO en modelos/base.joblib (no entrena nada) y clasifica frases.
Demuestra que la IA quedo guardada y se ejecuta en el PC.

Uso (desde la carpeta del proyecto):
  py entrenamiento/probar_modelo.py                      -> modo interactivo (linea vacia para salir)
  py entrenamiento/probar_modelo.py "frase 1" "frase 2"  -> clasifica esas frases y termina
"""

import json
import os
import sys

import joblib

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar

RUTA_MODELO = os.path.join(RAIZ, "modelos", "base.joblib")
RUTA_INFO = os.path.join(RAIZ, "modelos", "base_info.json")


def clasificar(modelo, frase):
    texto = normalizar(frase)
    probabilidades = modelo.predict_proba([texto])[0]
    i = probabilidades.argmax()
    return texto, modelo.classes_[i], probabilidades[i]


def mostrar(modelo, frase):
    texto, intencion, confianza = clasificar(modelo, frase)
    aviso = "  (conf < 0.5 -> 'no te entendi')" if confianza < 0.5 else ""
    print("  '{}' -> {}  (confianza {:.2f}){}".format(texto, intencion, confianza, aviso))


print("Cargando modelo desde disco: {}".format(os.path.normpath(RUTA_MODELO)))
modelo = joblib.load(RUTA_MODELO)
with open(RUTA_INFO, encoding="utf-8") as f:
    info = json.load(f)
print("Modelo: {}".format(info["modelo"]))
print("Entrenado el {} con {} frases. Accuracy test {}, F1 macro {}".format(
    info["fecha"], info["dataset"]["train"],
    info["metricas_test"]["accuracy"], info["metricas_test"]["f1_macro"]))
print("Intenciones: {}\n".format(", ".join(info["intenciones"])))

if len(sys.argv) > 1:
    for frase in sys.argv[1:]:
        mostrar(modelo, frase)
else:
    print("Escribe una frase (linea vacia para salir):")
    while True:
        frase = input("> ").strip()
        if not frase:
            break
        mostrar(modelo, frase)
