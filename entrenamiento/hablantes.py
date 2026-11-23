"""
hablantes.py
Verificacion de hablante con ECAPA-TDNN (speechbrain/spkrec-ecapa-voxceleb), sin conexion.
Lo usan enrolar_hablantes.py, evaluar_hablantes.py y, mas adelante, Doby.

  cargar_modelo()        modelo desde modelos/ecapa-voxceleb (HF_HUB_OFFLINE=1: nunca descarga)
  preparar(audio)        pasa_altos 100 Hz + recorte al tramo con voz + RMS de la voz a -20 dBFS
  embedding(modelo, a)   vector de 192 con norma 1 (a = salida de preparar)
  centroide(embs)        media normalizada; centroide_fuentes(): igual peso por fuente
  identificar(...)       coseno contra los centroides -> aceptado / repetir / desconocido
  cargar_hablantes()     centroides y umbrales guardados en modelos/hablantes/
  mezclar_ruido(...)     voz + ruido a una SNR dada (RMS contra RMS, ambos filtrados)

preparar() debe ser IGUAL al enrolar y al identificar: usa preproceso.pasa_altos(),
la unica implementacion del filtro.
"""

import json
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")             # nunca descargar modelos

import numpy as np

from preproceso import pasa_altos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA_MODELO = os.path.join(RAIZ, "modelos", "ecapa-voxceleb")
CARPETA_HABLANTES = os.path.join(RAIZ, "modelos", "hablantes")

TASA = 16000
TRAMO = 320                    # 20 ms
MAX_OFFSET_UMBRAL = 10.0       # voz = tramos sobre ruido + min(10 dB, (voz - ruido) / 2), como validar_audios
MARGEN = 0.1                   # s antes y despues del tramo con voz
VOZ_MINIMA = 0.5               # s; menos -> None (no hay voz suficiente)
RMS_OBJETIVO = -20.0           # dBFS de la voz: el volumen no debe ser una pista del hablante
PICO_MAXIMO = 0.99
VERSION_PREPARAR = 1           # cambiarla si cambia preparar(): invalida la cache de embeddings


# ---------------- Niveles ----------------
def a_flotante(audio):
    """int16 o float -> float64 en [-1, 1]."""
    audio = np.asarray(audio)
    if audio.dtype == np.int16:
        return audio.astype(np.float64) / 32768.0
    return audio.astype(np.float64)


def db_tramos(filtrado):
    n = len(filtrado) // TRAMO
    if n == 0:
        return np.zeros(0)
    rms = np.sqrt(np.mean(filtrado[:n * TRAMO].reshape(n, TRAMO) ** 2, axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-8))


def tramos_con_voz(filtrado):
    """Mascara de tramos de 20 ms con voz (umbral relativo al ruido de ESTE audio)."""
    db = db_tramos(filtrado)
    if len(db) == 0:
        return db.astype(bool)
    piso, voz = np.percentile(db, 10), np.percentile(db, 95)
    return db > piso + min(MAX_OFFSET_UMBRAL, (voz - piso) / 2)


def tramo_voz(audio, fs=TASA):
    """(inicio, fin) en segundos del tramo con voz, sin margen; None si no hay voz."""
    activos = np.where(tramos_con_voz(pasa_altos(a_flotante(audio), fs=fs)))[0]
    if len(activos) == 0:
        return None
    return activos[0] * TRAMO / fs, (activos[-1] + 1) * TRAMO / fs


def rms_filtrado(audio, fs=TASA, solo_voz=False):
    """RMS (lineal) del audio filtrado; con solo_voz, solo de los tramos con voz."""
    f = pasa_altos(a_flotante(audio), fs=fs)
    if solo_voz:
        mascara = tramos_con_voz(f)
        n = len(mascara)
        if mascara.any():
            f = f[:n * TRAMO].reshape(n, TRAMO)[mascara].ravel()
    return float(np.sqrt(np.mean(f ** 2))) if len(f) else 0.0


# ---------------- Preparacion ----------------
def preparar(audio, fs=TASA):
    """
    audio: int16 o float en [-1, 1], mono, 16 kHz.
    Devuelve float32: filtrado (pasa_altos 100 Hz), recortado al tramo con voz
    (+-0.1 s) y con el RMS de la voz a -20 dBFS (pico <= 0.99). None si hay
    menos de 0.5 s de voz.
    """
    f = pasa_altos(a_flotante(audio), fs=fs)
    mascara = tramos_con_voz(f)
    activos = np.where(mascara)[0]
    if len(activos) == 0 or (activos[-1] + 1 - activos[0]) * TRAMO / fs < VOZ_MINIMA:
        return None
    ini = max(0, activos[0] * TRAMO - int(MARGEN * fs))
    fin = min(len(f), (activos[-1] + 1) * TRAMO + int(MARGEN * fs))
    n = len(mascara)
    voz = f[:n * TRAMO].reshape(n, TRAMO)[mascara].ravel()
    rms = float(np.sqrt(np.mean(voz ** 2)))
    if rms <= 0:
        return None
    y = f[ini:fin] * (10 ** (RMS_OBJETIVO / 20) / rms)
    pico = float(np.max(np.abs(y)))
    if pico > PICO_MAXIMO:
        y *= PICO_MAXIMO / pico
    return y.astype(np.float32)


# ---------------- Ruido ----------------
def mezclar_ruido(voz, ruido, snr_db, fs=TASA):
    """
    voz + g * ruido (crudos, como los captaria el microfono) con g tal que
    RMS(voz filtrada, solo tramos con voz) / RMS(ruido filtrado) = snr_db.
    Se mide filtrado porque en el ruido crudo domina el vaiven < 20 Hz de la
    fuente, que pasa_altos quita. El ruido debe durar al menos lo que la voz.
    """
    voz = a_flotante(voz)
    ruido = a_flotante(ruido)[:len(voz)]
    rms_v = rms_filtrado(voz, fs, solo_voz=True)
    rms_r = rms_filtrado(ruido, fs)
    if rms_r <= 0:
        return voz.copy()
    g = rms_v / (rms_r * 10 ** (snr_db / 20))
    return np.clip(voz + g * ruido, -1.0, 32767 / 32768)


# ---------------- Modelo y embeddings ----------------
def cargar_modelo(dispositivo=None):
    """ECAPA desde modelos/ecapa-voxceleb, sin conexion. GPU si hay, si no CPU."""
    import torch
    from speechbrain.inference.speaker import EncoderClassifier
    from speechbrain.utils.fetching import LocalStrategy
    if dispositivo is None:
        dispositivo = "cuda:0" if torch.cuda.is_available() else "cpu"
    return EncoderClassifier.from_hparams(source=CARPETA_MODELO, savedir=CARPETA_MODELO,
                                          local_strategy=LocalStrategy.COPY,
                                          run_opts={"device": dispositivo})


def embedding(modelo, audio_preparado):
    """Embedding de 192 con norma 1 de un audio ya preparado."""
    import torch
    with torch.no_grad():
        x = torch.from_numpy(np.ascontiguousarray(audio_preparado, dtype=np.float32)).unsqueeze(0)
        e = modelo.encode_batch(x).squeeze().float().cpu().numpy()
    return e / np.linalg.norm(e)


def normalizar(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def centroide(embeddings):
    """Media de embeddings (norma 1) normalizada."""
    return normalizar(np.mean(np.asarray(embeddings), axis=0))


def centroide_fuentes(grupos):
    """Igual peso por fuente (ej. INMP441 y celular): centroide de los centroides no vacios."""
    return centroide([centroide(g) for g in grupos if len(g)])


# ---------------- Decision ----------------
def identificar(emb, centroides, nombres, umbral_alto, umbral_bajo):
    """
    Coseno contra cada centroide. Mejor similitud s:
      s >= umbral_alto               -> 'aceptado'  (nombre del mejor)
      umbral_bajo <= s < umbral_alto -> 'repetir'   (zona gris: Doby pide repetir)
      s < umbral_bajo                -> 'desconocido'
    """
    similitudes = np.asarray(centroides) @ emb
    i = int(np.argmax(similitudes))
    s = float(similitudes[i])
    estado = "aceptado" if s >= umbral_alto else "repetir" if s >= umbral_bajo else "desconocido"
    return {"nombre": nombres[i] if estado == "aceptado" else None, "mejor": nombres[i],
            "similitud": s, "estado": estado,
            "similitudes": {n: float(v) for n, v in zip(nombres, similitudes)}}


def cargar_hablantes(carpeta=CARPETA_HABLANTES):
    """(nombres, centroides, configuracion) guardados por enrolar_hablantes.py."""
    with open(os.path.join(carpeta, "hablantes.json"), encoding="utf-8") as f:
        config = json.load(f)
    centroides = np.load(os.path.join(carpeta, "centroides.npy"))
    return config["nombres"], centroides, config
