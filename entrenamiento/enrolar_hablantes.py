"""
enrolar_hablantes.py  -  CORRE EN EL PC
Enrolamiento final para Doby con la variante, el metodo y los umbrales que eligio
evaluar_hablantes.py (datos_voz/reportes/hablantes/evaluacion.json).

Uso:  py entrenamiento/evaluar_hablantes.py     (primero)
      py entrenamiento/enrolar_hablantes.py
      py entrenamiento/enrolar_hablantes.py --incluir-pruebas   # + tomas en sitio (probar_hablante --guardar)

- Usa TODAS las tomas usables del INMP441 de los integrantes (el 70/30 era solo para evaluar),
  mas el celular y/o el aumento con ruido si la variante elegida los incluye.
- --incluir-pruebas: suma las tomas de datos_voz/pruebas_hablante/ (registro.csv) cuya etiqueta
  EMPIEZA con el nombre de un integrante ("jenpol salon"), con la misma regla de descarte y el
  mismo aumento. Las demas etiquetas ("hermano", "impostor...", vacias) se omiten. Los umbrales NO
  se recalculan: se conservan los del enrolamiento actual (modelos/hablantes/hablantes.json).
- Los impostores (datos_voz/inmp441/impostor_NN/) nunca entran.
Salida: modelos/hablantes/centroides.npy, hablantes.json (+ clasificador.joblib si el metodo no es coseno).
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

import numpy as np

import conjunto_hablantes as c
import evaluar_hablantes as ev
import hablantes as h

RUTA_EVALUACION = os.path.join(ev.SALIDA, "evaluacion.json")
CARPETA_PRUEBAS = os.path.join(c.DATOS, "pruebas_hablante")


def tomas_en_sitio(integrantes):
    """(tomas, omitidas) de probar_hablante.py --guardar cuya etiqueta empieza con un integrante."""
    ruta_csv = os.path.join(CARPETA_PRUEBAS, "registro.csv")
    if not os.path.exists(ruta_csv):
        return [], []
    tomas, omitidas = [], []
    with open(ruta_csv, newline="", encoding="utf-8-sig") as f:
        filas = list(csv.DictReader(f))
    for fila in filas:
        palabras = (fila.get("etiqueta") or "").lower().split()
        persona = palabras[0] if palabras else ""
        if persona not in integrantes:
            omitidas.append((fila["archivo"], "etiqueta '{}' no es de un integrante".format(fila.get("etiqueta") or "")))
            continue
        ruta = os.path.join(CARPETA_PRUEBAS, fila["archivo"])
        if not os.path.exists(ruta):
            omitidas.append((fila["archivo"], "no existe el WAV"))
            continue
        audio = c.leer_wav(ruta)
        motivos = c.motivos_descarte(fila.get("huecos", ""), h.tramo_voz(audio))
        if not motivos and h.preparar(audio) is None:
            motivos.append("menos de {} s de voz".format(h.VOZ_MINIMA))
        if motivos:
            omitidas.append((fila["archivo"], "; ".join(motivos)))
            continue
        tomas.append({"persona": persona, "bloque": "S", "archivo": "sitio:" + fila["archivo"], "ruta": ruta,
                      "fuente": "inmp441", "audio": audio, "usable": True, "motivo": ""})
    return tomas, omitidas


def centroide_con_peso(grupo, sitio, peso):
    """
    grupo = [embeddings INMP441 (incluidas las tomas en sitio y su aumento), embeddings celular].
    El centroide del INMP441 es la media PONDERADA: cada embedding de 'sitio' pesa 'peso' y el resto 1.
    Despues, como siempre, igual peso por fuente (INMP441 / celular).
    """
    inmp, cel = grupo
    k = len(sitio)                      # las tomas en sitio van al final (tomas = base + en_sitio)
    assert k <= len(inmp) and (k == 0 or np.allclose(np.asarray(inmp[-k:]), np.asarray(sitio))), \
        "las tomas en sitio no estan al final del grupo"
    pesos = np.array([1.0] * (len(inmp) - k) + [peso] * k)
    media = (np.asarray(inmp) * pesos[:, None]).sum(axis=0) / pesos.sum()
    return h.centroide([h.normalizar(media)] + ([h.centroide(cel)] if len(cel) else []))


def main():
    parser = argparse.ArgumentParser(description="Enrolamiento final de los integrantes para Doby.")
    parser.add_argument("--incluir-pruebas", action="store_true",
                        help="sumar las tomas en sitio de datos_voz/pruebas_hablante/ (etiqueta = integrante ...)")
    parser.add_argument("--peso-pruebas", type=float, default=1.0,
                        help="con --incluir-pruebas: cada toma en sitio (y su aumento) cuenta como W tomas en el "
                             "centroide (1 = igual que las demas)")
    args = parser.parse_args()
    if args.peso_pruebas != 1.0 and not args.incluir_pruebas:
        parser.error("--peso-pruebas solo tiene sentido con --incluir-pruebas")
    if args.peso_pruebas <= 0:
        parser.error("--peso-pruebas debe ser mayor que 0")
    inicio = time.perf_counter()
    if not os.path.exists(RUTA_EVALUACION):
        sys.exit("Falta {}: corre primero evaluar_hablantes.py.".format(os.path.relpath(RUTA_EVALUACION, h.RAIZ)))
    with open(RUTA_EVALUACION, encoding="utf-8") as f:
        evaluacion = json.load(f)
    if evaluacion["version_preparar"] != h.VERSION_PREPARAR:
        sys.exit("La evaluacion se hizo con otra version de preparar(): vuelve a correr evaluar_hablantes.py.")
    variante, metodo = evaluacion["variante"], evaluacion["metodo"]

    integrantes, impostores = c.personas()
    if integrantes != evaluacion["integrantes"]:
        sys.exit("Los integrantes cambiaron desde la evaluacion ({} -> {}): vuelve a evaluar.".format(
            evaluacion["integrantes"], integrantes))
    tomas = [t for p in integrantes for t in c.tomas_inmp441(p) if t["usable"]]
    umbrales = (evaluacion["umbral_alto"], evaluacion["umbral_bajo"], evaluacion["base_umbral"])
    en_sitio = []
    if args.incluir_pruebas:
        en_sitio, omitidas = tomas_en_sitio(integrantes)
        print("Tomas en sitio: {} ({})".format(len(en_sitio), ", ".join(
            "{} {}".format(p, sum(t["persona"] == p for t in en_sitio)) for p in integrantes)))
        for archivo, motivo in omitidas:
            print("  omitida {}: {}".format(archivo, motivo))
        tomas += en_sitio
        ruta_actual = os.path.join(h.CARPETA_HABLANTES, "hablantes.json")
        if os.path.exists(ruta_actual):                     # los umbrales NO se recalculan: se conservan
            with open(ruta_actual, encoding="utf-8") as f:
                actual = json.load(f)
            umbrales = (actual["umbral_alto"], actual["umbral_bajo"], actual["base_umbral"])
    assert not any(c.PATRON_IMPOSTOR.match(t["persona"]) for t in tomas), "un impostor no puede enrolarse"
    celular = {p: c.tomas_celular(p) for p in integrantes}

    salida = h.CARPETA_HABLANTES
    if os.path.exists(os.path.join(salida, "hablantes.json")):
        if input("Ya hay un enrolamiento en {}. Sobrescribir? [s/N]: ".format(
                os.path.relpath(salida, h.RAIZ))).strip().lower() != "s":
            sys.exit("No se cambio nada.")
    os.makedirs(salida, exist_ok=True)

    print("Enrolando {} con {} + {} (todas las tomas usables)".format(", ".join(integrantes), variante, metodo))
    modelo = h.cargar_modelo()
    emb = ev.Embeddings(modelo, c.ruidos())
    todas = {t["archivo"] for t in tomas}
    grupos = ev.grupos_entrenamiento(integrantes, todas, {p: [t for t in tomas if t["persona"] == p] for p in integrantes},
                                     celular, emb, variante)
    if en_sitio and args.peso_pruebas != 1.0:
        if metodo != "coseno":
            sys.exit("--peso-pruebas solo esta implementado para el metodo coseno.")
        sitio = ev.grupos_entrenamiento(integrantes, todas, {p: [t for t in en_sitio if t["persona"] == p] for p in integrantes},
                                        {p: [] for p in integrantes}, emb, variante)
        centroides = np.stack([centroide_con_peso(grupos[p], sitio[p][0], args.peso_pruebas) for p in integrantes])
        print("Peso de las tomas en sitio: x{:g}".format(args.peso_pruebas))
    else:
        centroides = np.stack([h.centroide_fuentes(grupos[p]) for p in integrantes])
    emb.guardar()
    np.save(os.path.join(salida, "centroides.npy"), centroides)
    if metodo != "coseno":
        import joblib
        joblib.dump(ev.Decisor(metodo, grupos), os.path.join(salida, "clasificador.joblib"))

    config = {"nombres": integrantes, "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
              "variante": variante, "metodo": metodo,
              "umbral_alto": umbrales[0], "umbral_bajo": umbrales[1],
              "base_umbral": umbrales[2], "evaluacion": evaluacion["fecha"],
              "peso_pruebas": args.peso_pruebas if en_sitio else None,
              "tomas": {p: {"inmp441": sum(t["persona"] == p and t["bloque"] != "S" for t in tomas),
                            "en_sitio": sum(t["persona"] == p for t in en_sitio),
                            "celular": len(celular[p]) if ev.VARIANTES[variante]["celular"] else 0,
                            "aumento": ev.AUMENTOS_POR_TOMA if ev.VARIANTES[variante]["aumento"] else 0}
                        for p in integrantes},
              "preparar": {"version": h.VERSION_PREPARAR, "corte_hz": 100, "rms_objetivo_dbfs": h.RMS_OBJETIVO,
                           "voz_minima_s": h.VOZ_MINIMA},
              "modelo": "modelos/ecapa-voxceleb (speechbrain/spkrec-ecapa-voxceleb)"}
    with open(os.path.join(salida, "hablantes.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=1)
    print("Guardado en {}: centroides.npy, hablantes.json{}  (umbrales {:.3f} / {:.3f}, {:.1f} s)".format(
        os.path.relpath(salida, h.RAIZ), ", clasificador.joblib" if metodo != "coseno" else "",
        umbrales[0], umbrales[1], time.perf_counter() - inicio))


if __name__ == "__main__":
    main()
