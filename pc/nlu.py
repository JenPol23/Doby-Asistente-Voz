"""
nlu.py  -  CORRE EN EL PC
Clasificador de intenciones de Doby. CARGA el modelo guardado en
modelos/base.joblib (TF-IDF + LogisticRegression); nunca entrena al arrancar.

Uso:
  from nlu import Nlu
  nlu = Nlu()
  intencion, confianza = nlu.clasificar("prende el ventilador")   # texto ya normalizado
"""

import json
import os

import joblib

CARPETA_MODELOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modelos")
RUTA_MODELO = os.path.join(CARPETA_MODELOS, "base.joblib")
RUTA_INFO = os.path.join(CARPETA_MODELOS, "base_info.json")


class Nlu:
    def __init__(self, ruta_modelo=RUTA_MODELO, ruta_info=RUTA_INFO):
        print("Cargando modelo desde disco: {}".format(os.path.normpath(ruta_modelo)))
        self.modelo = joblib.load(ruta_modelo)
        with open(ruta_info, encoding="utf-8") as f:
            info = json.load(f)
        print("  Modelo: {}".format(info["modelo"]))
        print("  Entrenado el {} con {} frases. Accuracy test {}, F1 macro {}".format(
            info["fecha"], info["dataset"]["train"],
            info["metricas_test"]["accuracy"], info["metricas_test"]["f1_macro"]))

    def clasificar(self, texto_normalizado):
        """Devuelve (intencion, confianza) de la intencion mas probable."""
        probabilidades = self.modelo.predict_proba([texto_normalizado])[0]
        i = probabilidades.argmax()
        return self.modelo.classes_[i], float(probabilidades[i])
