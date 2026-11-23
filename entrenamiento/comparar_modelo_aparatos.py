"""
comparar_modelo_aparatos.py  -  CORRE EN EL PC
Compara el modelo de intenciones ACTUAL (modelos/base.joblib) con el CANDIDATO del cambio de aparatos
(modelos/candidato_aparatos/base.joblib). No reemplaza nada.

Uso:  py entrenamiento/comparar_modelo_aparatos.py [--candidato candidato_aparatos]

1. Test nuevo (datos/test.csv): accuracy y F1 macro de los dos. OJO: el modelo actual se entreno con el
   train VIEJO (respaldos/antes_cambio_aparatos_2026-10-06/datos/train.csv); se cuenta cuantas frases del
   test nuevo estaban en ese train (para el, esas frases no son nuevas).
2. Frases de la demo (datos/frases_demo.txt) con los dos.
3. Confianza en frases escritas de cautin y plancha, frente a UMBRAL de doby.py, con los criterios aprobados:
   - con verbo: mediana >= 0.7 y ninguna < 0.5 (y la intencion correcta);
   - sin verbo ("el soldador"): confianza < 0.5 o intencion que no sea encender ni apagar.
4. Lo mismo con lo que oyo Whisper en el paso 2 (resultados/whisper_aparatos.csv), solo las
   transcripciones distintas en las que el aparato se detecto bien (aparato_ok = 1).

Salida: consola y resultados/<candidato>/comparacion_aparatos.txt

Dependencias (por importacion, sin modificarlas): pc/doby.py (UMBRAL), pc/texto.py (normalizar).
"""

import argparse
import csv
import io
import os
import sys
from contextlib import redirect_stdout

import joblib
import numpy as np
from sklearn.metrics import accuracy_score, f1_score

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar          # noqa: E402

with redirect_stdout(io.StringIO()):
    import doby                       # noqa: E402  (solo UMBRAL)
UMBRAL = doby.UMBRAL
TRAIN_VIEJO = os.path.join(RAIZ, "respaldos", "antes_cambio_aparatos_2026-10-06", "datos", "train.csv")
MEDIANA_MINIMA = 0.7

# (frase escrita, intencion esperada). Grupos para los criterios.
CON_VERBO = [
    ("Prende el cautín.", "encender"), ("Enciende el cautín.", "encender"), ("Préndeme el cautín.", "encender"),
    ("Enciende el soldador.", "encender"), ("Prende el soldador.", "encender"),
    ("Prende la plancha.", "encender"), ("Enciende la plancha.", "encender"),
    ("Prende la plancha del pelo.", "encender"), ("Enciende la planchita.", "encender"),
    ("Prende la alisadora.", "encender"), ("Activa la plancha.", "encender"),
    ("Prende el cautín y la plancha.", "encender"), ("Prende la plancha y el ventilador.", "encender"),
    ("Enciende el bombillo y el cautín.", "encender"),
    ("Voy a soldar, prende el cautín.", "encender"), ("Me voy a alisar el pelo, prende la plancha.", "encender"),
    ("Apaga el cautín.", "apagar"), ("Apaga el soldador.", "apagar"), ("Apágame el soldador.", "apagar"),
    ("Apaga la plancha.", "apagar"), ("Apaga la plancha del pelo.", "apagar"), ("Apaga la planchita.", "apagar"),
    ("Apaga la alisadora.", "apagar"), ("Desactiva el cautín.", "apagar"),
    ("Apaga el cautín y la plancha.", "apagar"), ("Ya terminé de soldar, apaga el cautín.", "apagar"),
    ("¿Está prendido el cautín?", "consultar_estado"), ("¿Está encendida la plancha?", "consultar_estado"),
    ("El cautín sigue encendido.", "consultar_estado"), ("¿La plancha está apagada?", "consultar_estado"),
    ("¿Cómo está el soldador?", "consultar_estado"),
]
SIN_VERBO = ["El soldador.", "El cautín.", "La plancha.", "La planchita.", "La alisadora.",
             "La plancha del pelo.", "El ventilador.", "El bombillo."]          # los dos ultimos: referencia
CONTROL = [("Prende todo.", "regla: encender_todo"), ("Apaga todo.", "apagar_todo"), ("Apágalo.", "apagar"),
           ("¿Qué está encendido?", "consultar_estado"), ("Prende el ventilador.", "encender"),
           ("Apaga el bombillo.", "apagar"), ("Enciende el ventilador.", "encender"), ("Apaga la luz.", "apagar")]
RESALTAR = {"Apaga el soldador.", "Prende la plancha.", "El soldador."}

lineas = []


def salida(texto=""):
    print(texto)
    lineas.append(texto)


def predecir(modelo, textos):
    p = modelo.predict_proba([normalizar(t) for t in textos])
    i = p.argmax(axis=1)
    return [modelo.classes_[k] for k in i], p.max(axis=1)


def leer_csv(ruta):
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def tabla(titulo, frases, viejo, nuevo, sin_verbo=False):
    """Imprime la tabla y devuelve las confianzas del nuevo que cumplen / no cumplen el criterio."""
    textos = [f for f, _ in frases]
    pv, cv = predecir(viejo, textos)
    pn, cn = predecir(nuevo, textos)
    salida("\n=== {} ===".format(titulo))
    salida("  {:46} {:20} {:>24} {:>24}  {}".format("frase", "esperada", "ACTUAL", "CANDIDATO", "criterio"))
    fallos = []
    for (frase, esperada), a, ca, b, cb in zip(frases, pv, cv, pn, cn):
        if sin_verbo:
            ok = cb < UMBRAL or b not in ("encender", "apagar")
        elif esperada.startswith("regla"):
            ok = True                                   # "prende todo" lo decide doby.py antes del modelo
        else:
            ok = b == esperada and cb >= UMBRAL
        if not ok:
            fallos.append(frase)
        marca = "  <==" if frase in RESALTAR else ""
        salida("  {:46} {:20} {:>17} {:5.2f} {:>17} {:5.2f}  {}{}".format(
            frase, esperada, a, ca, b, cb, "OK" if ok else "NO", marca))
    return cn, fallos


def main():
    parser = argparse.ArgumentParser(description="Compara el modelo actual con el candidato")
    parser.add_argument("--candidato", default="candidato_aparatos")
    args = parser.parse_args()
    viejo = joblib.load(os.path.join(RAIZ, "modelos", "base.joblib"))
    nuevo = joblib.load(os.path.join(RAIZ, "modelos", args.candidato, "base.joblib"))
    salida("Modelo ACTUAL: modelos/base.joblib   CANDIDATO: modelos/{}/base.joblib   UMBRAL de Doby: {}".format(
        args.candidato, UMBRAL))

    # ---- 1. Test nuevo ----
    test = leer_csv(os.path.join(RAIZ, "datos", "test.csv"))
    x, y = [f["texto"] for f in test], [f["intencion"] for f in test]
    vistos = {normalizar(f["texto"]) for f in leer_csv(TRAIN_VIEJO)}
    en_train_viejo = sum(1 for t in x if t in vistos)
    salida("\n=== 1. Test nuevo ({} frases) ===".format(len(x)))
    salida("  Referencia (modelo actual en SU test, 24-sep): accuracy 0.9865, F1 macro 0.9871")
    for nombre, m in (("ACTUAL", viejo), ("CANDIDATO", nuevo)):
        p = m.predict(x)
        salida("  {:9} accuracy {:.4f}   F1 macro {:.4f}".format(nombre, accuracy_score(y, p),
                                                                f1_score(y, p, average="macro")))
    salida("  OJO: {} de {} frases del test nuevo estaban en el train del modelo ACTUAL (las vio al entrenar)."
           .format(en_train_viejo, len(x)))
    sin_vistas = [i for i, t in enumerate(x) if t not in vistos]
    for nombre, m in (("ACTUAL", viejo), ("CANDIDATO", nuevo)):
        p = m.predict([x[i] for i in sin_vistas])
        salida("  {:9} solo en las {} que el ACTUAL no vio: accuracy {:.4f}   F1 macro {:.4f}".format(
            nombre, len(sin_vistas), accuracy_score([y[i] for i in sin_vistas], p),
            f1_score([y[i] for i in sin_vistas], p, average="macro")))

    # ---- 2. Demo ----
    with open(os.path.join(RAIZ, "datos", "frases_demo.txt"), encoding="utf-8") as f:
        demo = [tuple(p.strip() for p in l.rsplit(";", 1)) for l in f if ";" in l]
    salida("\n=== 2. Frases de la demo ({}) ===".format(len(demo)))
    for nombre, m in (("ACTUAL", viejo), ("CANDIDATO", nuevo)):
        p, c = predecir(m, [d[0] for d in demo])
        buenas = sum(a == d[1] for a, d in zip(p, demo))
        bajas = [d[0] for d, cc in zip(demo, c) if cc < UMBRAL]
        salida("  {:9} {}/{}   con confianza < {}: {}".format(nombre, buenas, len(demo), UMBRAL, bajas or "ninguna"))

    # ---- 3. Frases escritas ----
    cn, fallos_v = tabla("3a. Cautin y plancha CON verbo (criterio: intencion correcta, mediana >= {}, ninguna < {})"
                         .format(MEDIANA_MINIMA, UMBRAL), CON_VERBO, viejo, nuevo)
    mediana = float(np.median(cn))
    salida("  CANDIDATO: mediana {:.2f}, minima {:.2f}, fallos {}  -> {}".format(
        mediana, float(np.min(cn)), fallos_v or "ninguno",
        "CUMPLE" if mediana >= MEDIANA_MINIMA and not fallos_v else "NO CUMPLE"))
    _, fallos_s = tabla("3b. SIN verbo (criterio: confianza < {} o intencion que no sea encender/apagar)".format(UMBRAL),
                        [(f, "(no encender/apagar)") for f in SIN_VERBO], viejo, nuevo, sin_verbo=True)
    salida("  CANDIDATO: {}".format("CUMPLE" if not fallos_s else "NO CUMPLE: {}".format(fallos_s)))
    _, fallos_c = tabla("3c. Ordenes que ya funcionaban (control)", CONTROL, viejo, nuevo)
    salida("  CANDIDATO: {}".format("todas bien" if not fallos_c else "fallan: {}".format(fallos_c)))

    # ---- 4. Lo que oyo Whisper en el paso 2 ----
    ruta = os.path.join(RAIZ, "resultados", "whisper_aparatos.csv")
    if os.path.exists(ruta):
        filas = [r for r in leer_csv(ruta) if r["aparato_ok"] == "1" and r["whisper"].strip()]
        salida("\n=== 4. Transcripciones REALES de Whisper (paso 2; distintas, con el aparato bien detectado) ===")
        salida("  {:4} {:36} {:>5} {:22} {:>8} {:>8} {:>8}  {}".format(
            "id", "frase", "n", "esperada", "min", "mediana", "<umbral", "intenciones del CANDIDATO"))
        for id_ in dict.fromkeys(r["id"] for r in filas):
            sel = [r for r in filas if r["id"] == id_]
            distintas = sorted({normalizar(r["whisper"]) for r in sel})
            p, c = predecir(nuevo, distintas)
            esperada = sel[0]["intencion_esperada"] or "(sin verbo)"
            cuenta = {}
            for i in p:
                cuenta[i] = cuenta.get(i, 0) + 1
            salida("  {:4} {:36} {:5d} {:22} {:8.2f} {:8.2f} {:8d}  {}".format(
                id_, sel[0]["texto"], len(distintas), esperada, float(np.min(c)), float(np.median(c)),
                int(np.sum(c < UMBRAL)), ", ".join("{} x{}".format(k, v) for k, v in cuenta.items())))
            for t, i, cc in zip(distintas, p, c):
                if cc < UMBRAL or (esperada not in ("(sin verbo)",) and not esperada.startswith("regla") and i != esperada):
                    salida("         - '{}' -> {} {:.2f}".format(t, i, cc))

    destino = os.path.join(RAIZ, "resultados", args.candidato, "comparacion_aparatos.txt")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n")
    print("\nGuardado:", os.path.relpath(destino, RAIZ))


if __name__ == "__main__":
    main()
