"""
generar_voces_clonadas.py  -  CORRE EN EL PC
Genera con XTTS v2 todas las frases de Doby (pc/tts.py) con la voz de cada integrante.

Uso:  py entrenamiento/generar_voces_clonadas.py                 # todas las personas con referencia
      py entrenamiento/generar_voces_clonadas.py --persona lina
      py entrenamiento/generar_voces_clonadas.py --persona lina --rehacer

- Referencia: clips del bloque D con uso=referencia_voz (datos_voz/reportes/segmentos_<nombre>.csv,
  de validar_audios.py), de mayor SNR a menor, hasta sumar 10-20 s.
- Control de calidad: el Whisper de Doby (pc/stt.py) transcribe cada version; hasta 3 versiones
  por frase y se conserva la que mas se parece al texto. Tambien se mide la similitud de voz con
  ECAPA contra el centroide de la persona (solo informativo).
- Textos: pc/voz_clonada.py (ninguna frase clonada contiene "Doby").
- Salida: voz_cache_clonada/<persona>/<clave>_<md5>.wav + frases.csv + referencia.txt.
  Las frases que ya existen no se regeneran (salvo --rehacer).
- XTTS: modelo en %LOCALAPPDATA%/tts (coqui-tts), COQUI_TOS_AGREED=1 (uso academico), sin conexion.
  Las referencias se leen con 'wave' en vez de torchaudio.load (que necesita FFmpeg).
"""

import argparse
import csv
import os
import sys
import time
import wave
import zlib
from difflib import SequenceMatcher
from math import gcd

os.environ.setdefault("COQUI_TOS_AGREED", "1")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))

import stt as modulo_stt              # noqa: E402  (importa torch antes que faster_whisper)
import torch                          # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

import hablantes as h                 # noqa: E402
import tts                            # noqa: E402
import voz_clonada as vc              # noqa: E402
from texto import normalizar          # noqa: E402

MODELO_XTTS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "tts", "tts_models--multilingual--multi-dataset--xtts_v2")
REF_MIN, REF_MAX = 10.0, 20.0
MAX_INTENTOS = 3
SIM_BUENA = 0.95                      # con esta similitud no se generan mas versiones
SIM_REVISAR = 0.90                    # por debajo: escucharla antes de usarla
TEMPERATURA = 0.7
COLUMNAS = ["clave", "texto", "archivo", "intento", "intentos", "whisper", "similitud", "voz_ecapa_propia",
            "duracion_s", "seg_generacion", "revisar"]


def referencias(persona):
    """Clips del bloque D con uso=referencia_voz, de mayor SNR a menor, hasta 10-20 s."""
    ruta_csv = os.path.join(RAIZ, "datos_voz", "reportes", "segmentos_{}.csv".format(persona))
    if not os.path.exists(ruta_csv):
        return [], 0.0
    with open(ruta_csv, encoding="utf-8-sig") as f:
        filas = [r for r in csv.DictReader(f) if r["bloque"] == "D" and r["uso"] == "referencia_voz" and r["archivo"]]
    filas.sort(key=lambda r: (-float(r["snr_db"]), -float(r["similitud"] or 0)))
    elegidos, total = [], 0.0
    for r in filas:
        ruta = os.path.join(RAIZ, "datos_voz", "procesados", persona, r["archivo"].replace(" (existente)", ""))
        with wave.open(ruta) as w:
            dur = w.getnframes() / w.getframerate()
        if total + dur > REF_MAX and total >= REF_MIN:
            continue
        elegidos.append((ruta, dur, float(r["snr_db"])))
        total += dur
        if total >= REF_MIN:
            break
    return elegidos, total


def cargar_xtts():
    import torchaudio
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models import xtts as modulo_xtts

    def load_audio_wav(ruta, sampling_rate):
        """Reemplazo de xtts.load_audio: torchaudio.load necesita FFmpeg. Nuestros WAV son PCM mono."""
        with wave.open(str(ruta)) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
        audio = torch.from_numpy(x).unsqueeze(0)
        return torchaudio.functional.resample(audio, sr, sampling_rate) if sr != sampling_rate else audio

    modulo_xtts.load_audio = load_audio_wav
    cfg = XttsConfig()
    cfg.load_json(os.path.join(MODELO_XTTS, "config.json"))
    modelo = modulo_xtts.Xtts.init_from_config(cfg)
    modelo.load_checkpoint(cfg, checkpoint_dir=MODELO_XTTS, use_deepspeed=False)
    return modelo.cuda() if torch.cuda.is_available() else modelo


def a_16k_int16(wav24):
    g = gcd(16000, 24000)
    return tts._pulir(resample_poly(np.asarray(wav24, dtype=np.float64), 16000 // g, 24000 // g))


def parecido(a, b):
    return SequenceMatcher(None, normalizar(a), normalizar(b)).ratio()


def leer_manifiesto(ruta):
    if not os.path.exists(ruta):
        return {}
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        return {r["clave"]: r for r in csv.DictReader(f)}


def generar_persona(persona, xtts, stt, ecapa, centroide, rehacer):
    refs, total = referencias(persona)
    if total < REF_MIN:
        print("{}: sin referencia suficiente del bloque D ({:.1f} s). Se omite.".format(persona, total))
        return None
    carpeta = os.path.join(vc.CARPETA, persona)
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "referencia.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join("{}\t{:.1f} s\tSNR {:.0f} dB".format(os.path.relpath(r, RAIZ), d, s) for r, d, s in refs) + "\n")
    print("\n=== {}: referencia {:.1f} s ({})".format(persona, total, ", ".join(os.path.basename(r) for r, _, _ in refs)))
    lat, spk = xtts.get_conditioning_latents(audio_path=[r for r, _, _ in refs])

    ruta_manifiesto = os.path.join(carpeta, "frases.csv")
    manifiesto = leer_manifiesto(ruta_manifiesto)
    for clave in tts.FRASES:
        ruta = vc.ruta(persona, clave)
        if os.path.exists(ruta) and not rehacer and clave in manifiesto:
            continue
        texto = vc.texto(clave)
        mejor, intentos, t_total = None, 0, 0.0
        for intento in range(1, MAX_INTENTOS + 1):
            torch.manual_seed(zlib.crc32("{}|{}|{}".format(persona, clave, intento).encode()))
            t = time.perf_counter()
            salida = xtts.inference(texto, "es", lat, spk, temperature=TEMPERATURA, enable_text_splitting=True)
            t_total += time.perf_counter() - t
            pcm = a_16k_int16(salida["wav"])
            oido = stt.transcribir(pcm.astype(np.float32) / 32768)
            sim = parecido(oido, texto)
            intentos = intento
            if mejor is None or sim > mejor[0]:
                mejor = (sim, pcm, oido, intento)
            if sim >= SIM_BUENA:
                break
        sim, pcm, oido, intento = mejor
        with wave.open(ruta, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm.astype("<i2").tobytes())
        listo = h.preparar(pcm)
        voz = float(h.embedding(ecapa, listo) @ centroide) if listo is not None and centroide is not None else float("nan")
        manifiesto[clave] = {"clave": clave, "texto": texto, "archivo": os.path.relpath(ruta, RAIZ), "intento": intento,
                             "intentos": intentos, "whisper": oido, "similitud": "{:.2f}".format(sim),
                             "voz_ecapa_propia": "{:.2f}".format(voz), "duracion_s": "{:.2f}".format(len(pcm) / 16000),
                             "seg_generacion": "{:.2f}".format(t_total / intentos),
                             "revisar": "sí" if sim < SIM_REVISAR else "no"}
        print("  {:24s} {} intento(s)  similitud {:.2f}  voz {:.2f}  '{}'".format(clave, intentos, sim, voz, oido))
        with open(ruta_manifiesto, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.DictWriter(f, fieldnames=COLUMNAS)
            escritor.writeheader()
            escritor.writerows(manifiesto[c] for c in tts.FRASES if c in manifiesto)
    return manifiesto


def main():
    parser = argparse.ArgumentParser(description="Voces clonadas de Doby con XTTS v2.")
    parser.add_argument("--persona", help="solo esta persona (por defecto: todas las que tengan referencia)")
    parser.add_argument("--rehacer", action="store_true", help="regenerar aunque la frase ya exista")
    args = parser.parse_args()

    if args.persona:
        personas = [args.persona.lower()]
    else:
        personas = sorted(p[len("segmentos_"):-4] for p in os.listdir(os.path.join(RAIZ, "datos_voz", "reportes"))
                          if p.startswith("segmentos_") and p.endswith(".csv"))
    stt = modulo_stt.Stt()
    print("Cargando XTTS v2...")
    xtts = cargar_xtts()
    ecapa = h.cargar_modelo()
    try:
        nombres, centroides, _ = h.cargar_hablantes()
    except FileNotFoundError:
        nombres, centroides = [], None
    for persona in personas:
        centroide = centroides[nombres.index(persona)] if centroides is not None and persona in nombres else None
        generar_persona(persona, xtts, stt, ecapa, centroide, args.rehacer)


if __name__ == "__main__":
    main()
