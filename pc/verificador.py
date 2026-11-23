"""
verificador.py  -  CORRE EN EL PC
Verificacion de hablante para Doby (config.VERIFICAR_HABLANTE, solo modo voz).
La verificacion en si es entrenamiento/hablantes.py (preparar, embedding, identificar,
cargar_hablantes); aqui solo se carga y calienta el modelo, se combina el segundo
intento de la zona gris y se registra cada decision en logs/.
"""

import csv
import os
import sys
import time
from datetime import datetime

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "entrenamiento"))

import config                    # noqa: E402
import hablantes as h            # noqa: E402  (fija HF_HUB_OFFLINE=1: nunca descarga)

CARPETA_LOGS = os.path.join(RAIZ, "logs")
SEG_REPETIR = 15.0               # el segundo "Hola Doby" debe llegar antes de esto
COLUMNAS = ["fecha", "tipo", "regla", "persona_activa", "texto_whisper", "combinado", "seg_voz", "similitudes",
            "mejor", "similitud", "decision", "persona", "ms", "umbral_alto", "umbral_bajo", "umbral_sesion", "nota"]


def ruta_libre(ruta):
    """El CSV del dia; si ya existe con otras columnas (version anterior), <nombre>_2.csv, _3..."""
    base, ext = os.path.splitext(ruta)
    candidata, n = ruta, 1
    while os.path.exists(candidata):
        with open(candidata, newline="", encoding="utf-8-sig") as f:
            if next(csv.reader(f), None) == COLUMNAS:
                return candidata
        n += 1
        candidata = "{}_{}{}".format(base, n, ext)
    return candidata


class Verificador:
    def __init__(self, carpeta=None):
        self.nombres, self.centroides, cfg = h.cargar_hablantes(carpeta or h.CARPETA_HABLANTES)
        if cfg["metodo"] != "coseno":
            raise ValueError("Doby solo usa el metodo coseno (enrolado con {})".format(cfg["metodo"]))
        if cfg["preparar"]["version"] != h.VERSION_PREPARAR:
            raise ValueError("el enrolamiento es de otra version de preparar(): corre enrolar_hablantes.py")
        self.alto, self.bajo = cfg["umbral_alto"], cfg["umbral_bajo"]
        t = time.perf_counter()
        self.modelo = h.cargar_modelo()
        ruido = (1e-4 * np.random.default_rng(0).standard_normal(h.TASA)).astype(np.float32)
        h.embedding(self.modelo, ruido)          # calentamiento: la 1.a inferencia tarda varios segundos
        print("  ECAPA listo en {} ({:.1f} s con calentamiento). Integrantes: {}. Umbrales {:.3f} / {:.3f}".format(
            self.modelo.device, time.perf_counter() - t, ", ".join(self.nombres), self.alto, self.bajo))
        self.pendiente = None                    # (audio preparado o None, instante) del 1er intento en zona gris
        os.makedirs(CARPETA_LOGS, exist_ok=True)
        self.ruta_log = ruta_libre(os.path.join(CARPETA_LOGS, "verificacion_{}.csv".format(
            datetime.now().strftime("%Y-%m-%d"))))

    def cancelar(self):
        """La frase siguiente no fue 'Hola Doby': se olvida el intento en zona gris."""
        self.pendiente = None

    def verificar(self, audio, texto, tipo, persona_activa=None):
        """
        audio: el de escuchar_frase, antes de normalizar_volumen. tipo: 'llamado' u 'orden'.
        Devuelve el dict de hablantes.identificar() con estado aceptado / repetir / desconocido.
        Llamado en zona gris: se guarda; si otro llamado llega antes de 15 s, se decide con los
        dos audios preparados y concatenados (sin segunda zona gris). Orden: zona gris = desconocido.
        Orden con persona_activa (regla de sesion): se acepta si el mejor integrante ES persona_activa
        y su similitud >= config.UMBRAL_SESION. Si el mejor es otro integrante (aunque supere el umbral
        alto) se rechaza: para cambiar de persona hay que decir "Hola Doby ..." (regla del llamado).
        """
        inicio = time.perf_counter()
        listo, combinado, nota = h.preparar(audio), False, ""
        if tipo == "llamado" and self.pendiente is not None:
            anterior, cuando = self.pendiente
            self.pendiente = None
            if time.perf_counter() - cuando <= SEG_REPETIR:
                combinado = True
                partes = [a for a in (anterior, listo) if a is not None]
                listo = np.concatenate(partes) if partes else None
        if listo is None:
            nota = "menos de {} s de voz".format(h.VOZ_MINIMA)
            r = {"nombre": None, "mejor": "", "similitud": float("nan"), "estado": "repetir", "similitudes": {},
                 "sin_voz": True}          # audio demasiado corto: no es un rechazo de la voz (lo usa doby.py)
        else:
            r = h.identificar(h.embedding(self.modelo, listo), self.centroides, self.nombres, self.alto, self.bajo)
            if tipo == "orden" and persona_activa:
                r, nota = self.regla_sesion(r, persona_activa)
        if r["estado"] == "repetir":
            if tipo == "llamado" and not combinado:
                self.pendiente = (listo, time.perf_counter())
            else:
                r["estado"] = "desconocido"
        ms = 1000 * (time.perf_counter() - inicio)
        print("  Hablante{}: {} -> {}{} ({:.0f} ms){}".format(
            " (2 intentos)" if combinado else "",
            " | ".join("{} {:.3f}".format(n, s) for n, s in r["similitudes"].items()) or "sin voz",
            r["estado"].upper(), " " + r["nombre"] if r["nombre"] else "", ms, "  " + nota if nota else ""))
        seg_voz = 0.0 if listo is None else max(0.0, len(listo) / h.TASA - 2 * h.MARGEN)
        regla = "sesion" if tipo == "orden" and persona_activa else "estricta"
        self.registrar(r, ms, texto, tipo, combinado, nota, seg_voz, regla, persona_activa)
        return r

    def regla_sesion(self, r, persona):
        """(resultado, nota) de una orden con persona_activa."""
        mejor, s = r["mejor"], r["similitud"]
        if mejor == persona and s >= config.UMBRAL_SESION:
            return dict(r, estado="aceptado", nombre=persona), ""
        nota = "otro integrante ({} {:.3f}): debe decir Hola Doby".format(mejor, s) if mejor != persona and s >= self.alto else ""
        return dict(r, estado="desconocido", nombre=None), nota

    def registrar(self, r, ms, texto, tipo, combinado, nota, seg_voz, regla, persona_activa):
        """Una fila por verificacion en logs/verificacion_<fecha>.csv. Un error aqui no detiene a Doby."""
        fila = {"fecha": datetime.now().isoformat(sep=" ", timespec="seconds"), "tipo": tipo, "regla": regla,
                "persona_activa": persona_activa or "", "seg_voz": "{:.2f}".format(seg_voz),
                "umbral_sesion": "{:.4f}".format(config.UMBRAL_SESION),
                "texto_whisper": texto, "combinado": "si" if combinado else "no",
                "similitudes": ";".join("{}={:.4f}".format(n, s) for n, s in r["similitudes"].items()),
                "mejor": r["mejor"], "similitud": "" if np.isnan(r["similitud"]) else "{:.4f}".format(r["similitud"]),
                "decision": r["estado"], "persona": r["nombre"] or "", "ms": "{:.0f}".format(ms),
                "umbral_alto": "{:.4f}".format(self.alto), "umbral_bajo": "{:.4f}".format(self.bajo), "nota": nota}
        try:
            nuevo = not os.path.exists(self.ruta_log)
            with open(self.ruta_log, "a", newline="", encoding="utf-8-sig") as f:
                escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
                if nuevo:
                    escritor.writeheader()
                escritor.writerow(fila)
        except OSError as e:
            print("  AVISO: no se pudo escribir el registro de verificacion ({}).".format(e))
