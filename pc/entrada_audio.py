"""
entrada_audio.py  -  CORRE EN EL PC
Deteccion de voz con el microfono de la ESP32 (orden MIC del protocolo).

- Siempre hay 2 pedidos MIC en vuelo: mientras llega un bloque, la ESP32 ya
  tiene el siguiente pedido y no se pierde audio entre bloques.
- Conversion: muestra >> 16 y quitar la media (verificado en hardware).
- Calibracion con 2 s de ruido:
  umbral = max(3 x mediana, 1.5 x percentil 95, 400), con techo de 2000
  (la mediana ignora una tos; el percentil 95 cubre los picos del ruido del
  cuarto; el techo evita que Doby quede sordo: la voz esta alrededor de 4300).
- Umbral adaptativo: mientras espera una frase, recalcula el umbral cada 1 s
  con los bloques de ese momento (sube si se prende el ventilador,
  baja cuando se apagan). UMBRAL_MANUAL de config.py tiene prioridad.
- recalibrar(): despues de mover reles, escucha 1 s y rehace el umbral con el
  ruido nuevo (ej. el ventilador ya sonando): min(1200, max(3 x mediana, 400)).
- Red de seguridad: si una frase llega a los 8 s, el ruido estaba sobre el
  umbral -> umbral = min(2000, max(umbral, 2 x mediana de esa frase)).
- Frase: empieza con un bloque sobre el umbral (se guardan 0.3 s previos),
  termina con 0.8 s bajo el umbral o a los 8 s. Menos de 0.4 s de voz se descarta.
- Al terminar cada frase se vacian los MIC pendientes, para que el socket quede
  libre para HABLAR y RELE.
- normalizar_volumen(): lleva el pico de la frase a 0.9 (ganancia maxima x10)
  antes de Whisper, para que una voz baja o lejana no parezca silencio.
"""

import time
from collections import deque

import numpy as np

import config

MUESTRAS_BLOQUE = 1024                                    # un MIC = 64 ms
SEG_BLOQUE = MUESTRAS_BLOQUE / config.TASA
EN_VUELO = 2                                              # pedidos MIC adelantados

SEG_CALIBRACION = 2.0
FACTOR_MEDIANA = 3
FACTOR_P95 = 1.5
UMBRAL_MINIMO = 400
UMBRAL_TECHO = 2000
TECHO_RECALIBRAR = 1200      # tras conmutar un rele hay ruido momentaneo muy alto
BLOQUES_ADAPTA = round(1.0 / SEG_BLOQUE)                  # recalcular cada 1 s (16 bloques)
CAMBIO_AVISO = 0.20                                       # imprimir si cambia mas de 20 %
FACTOR_FRASE_LARGA = 2                                    # frase de 8 s: 2 x mediana
BLOQUES_PREVIOS = round(0.3 / SEG_BLOQUE)                 # 5 bloques
BLOQUES_SILENCIO = int(np.ceil(0.8 / SEG_BLOQUE))         # 13 bloques
BLOQUES_MAXIMO = int(np.ceil(8.0 / SEG_BLOQUE))           # 125 bloques
SEG_VOZ_MINIMA = 0.4
PICO_OBJETIVO = 0.9                                       # normalizacion antes de Whisper
GANANCIA_MAXIMA = 10.0


def normalizar_volumen(audio):
    """Lleva el pico de la frase a 0.9 (ganancia maxima x10). Devuelve (audio, ganancia)."""
    pico = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if pico == 0:
        return audio, 1.0
    ganancia = min(GANANCIA_MAXIMA, PICO_OBJETIVO / pico)
    return audio * ganancia, ganancia


class EntradaAudio:
    def __init__(self, esp):
        self.esp = esp
        self.pendientes = 0          # MIC enviados cuya respuesta no se ha leido
        self.ruido = None
        self.umbral = UMBRAL_MINIMO
        self.niveles_espera = []     # niveles de los bloques sin voz, para adaptar el umbral
        self.nivel_voz = None        # de la ultima frase: nivel promedio de los bloques con voz
        self.umbral_frase = None     # de la ultima frase: umbral con que se detecto

    # ---------------- Bloques del microfono ----------------
    def _bloque(self):
        """Devuelve (muestras float32 sin convertir la media, nivel del bloque)."""
        while True:
            try:
                while self.pendientes < EN_VUELO:
                    self.esp.pedir_mic()
                    self.pendientes += 1
                crudo = self.esp.recibir_mic()
                self.pendientes -= 1
                break
            except (OSError, ConnectionError) as e:
                print("Se perdio la conexion con el microfono ({}). Reconectando...".format(e))
                self.esp.conectar()
                self.pendientes = 0

        muestras = (crudo >> 16).astype(np.float32)        # los 16 bits mas importantes
        nivel = float(np.mean(np.abs(muestras - muestras.mean())))
        return muestras, nivel

    def vaciar(self):
        """Lee y bota las respuestas MIC pendientes: el socket queda libre."""
        try:
            while self.pendientes > 0:
                self.esp.recibir_mic()
                self.pendientes -= 1
        except (OSError, ConnectionError) as e:
            print("Se perdio la conexion al vaciar el microfono ({}). Reconectando...".format(e))
            self.esp.conectar()
            self.pendientes = 0

    def descartar(self, segundos):
        """Bota 'segundos' de microfono (ej. 0.3 s despues de que Doby habla)."""
        for _ in range(int(np.ceil(segundos / SEG_BLOQUE))):
            self._bloque()
        self.vaciar()

    # ---------------- Calibracion ----------------
    @staticmethod
    def _umbral_de(niveles):
        """Devuelve (mediana, percentil 95, umbral) de una lista de niveles de ruido."""
        mediana = float(np.median(niveles))
        p95 = float(np.percentile(niveles, 95))
        umbral = max(FACTOR_MEDIANA * mediana, FACTOR_P95 * p95, UMBRAL_MINIMO)
        return mediana, p95, min(umbral, UMBRAL_TECHO)

    def calibrar(self, segundos=SEG_CALIBRACION):
        """Mide el ruido del cuarto y fija el umbral. Devuelve el umbral."""
        niveles = [self._bloque()[1] for _ in range(round(segundos / SEG_BLOQUE))]
        self.vaciar()
        self.niveles_espera = []
        self.ruido, p95, calibrado = self._umbral_de(niveles)
        print("Ruido: mediana {:.0f}   percentil 95 {:.0f}   maximo {:.0f}   Umbral calibrado: {:.0f}".format(
            self.ruido, p95, max(niveles), calibrado))
        if config.UMBRAL_MANUAL is not None:
            self.umbral = float(config.UMBRAL_MANUAL)
            print("Se usa UMBRAL_MANUAL de config.py: {:.0f} (sin umbral adaptativo)".format(self.umbral))
        else:
            self.umbral = calibrado
        return self.umbral

    def recalibrar(self, segundos):
        """
        Escucha 'segundos' (en vez del descarte normal) y rehace el umbral con
        esos bloques. Se usa despues de mover reles: cambio el ruido del cuarto.
        """
        niveles = [self._bloque()[1] for _ in range(int(np.ceil(segundos / SEG_BLOQUE)))]
        self.vaciar()
        if config.UMBRAL_MANUAL is not None:
            return
        # Solo la mediana (sin percentil 95): si el usuario habla en este
        # segundo, su voz no sube el umbral.
        anterior = self.umbral
        self.ruido = float(np.median(niveles))
        self.umbral = min(TECHO_RECALIBRAR, max(FACTOR_MEDIANA * self.ruido, UMBRAL_MINIMO))
        self.niveles_espera = []
        print("  umbral recalibrado {:.0f} -> {:.0f} (cambio el ruido; mediana {:.0f})".format(
            anterior, self.umbral, self.ruido))

    def _adaptar(self, nivel):
        """Guarda el nivel de un bloque sin voz y cada 1 s recalcula el umbral."""
        if config.UMBRAL_MANUAL is not None:
            return
        self.niveles_espera.append(nivel)
        if len(self.niveles_espera) < BLOQUES_ADAPTA:
            return
        self.ruido, p95, nuevo = self._umbral_de(self.niveles_espera)
        self.niveles_espera = []
        if abs(nuevo - self.umbral) > CAMBIO_AVISO * self.umbral:
            print("  (umbral {:.0f} -> {:.0f}; ruido: mediana {:.0f}, percentil 95 {:.0f})".format(
                self.umbral, nuevo, self.ruido, p95))
        self.umbral = nuevo

    # ---------------- Una frase ----------------
    def escuchar_frase(self, al_esperar=None):
        """
        Espera una frase y la devuelve como
        (audio float32 en [-1, 1] a 16 kHz, segundos de voz, instante del ultimo
        bloque con voz segun time.perf_counter()).
        al_esperar: funcion opcional que se llama en cada bloque mientras NO hay voz (Doby: apagado
        automatico). Si devuelve True (uso el socket: vaciar(), RELE, HABLAR), se botan los bloques
        guardados y se sigue esperando. Sin ella, todo igual que antes.
        """
        previos = deque(maxlen=BLOQUES_PREVIOS)
        frase = None
        while True:
            muestras, nivel = self._bloque()
            ahora = time.perf_counter()

            if frase is None:                        # esperando que empiece la voz
                if al_esperar is not None and al_esperar():
                    previos.clear()
                    continue
                if nivel > self.umbral:
                    frase = list(previos) + [muestras]
                    niveles_frase = [nivel]
                    inicio = len(frase) - 1          # indice del primer bloque con voz
                    ultimo = inicio                  # indice del ultimo bloque con voz
                    t_ultima_voz = ahora
                    silencio = 0
                else:
                    previos.append(muestras)
                    self._adaptar(nivel)
                continue

            frase.append(muestras)
            niveles_frase.append(nivel)
            if nivel > self.umbral:
                ultimo = len(frase) - 1
                t_ultima_voz = ahora
                silencio = 0
            else:
                silencio += 1

            if silencio < BLOQUES_SILENCIO and len(frase) - inicio < BLOQUES_MAXIMO:
                continue

            self.umbral_frase = self.umbral
            voz = [n for n in niveles_frase[:ultimo - inicio + 1] if n > self.umbral]
            self.nivel_voz = float(np.mean(voz)) if voz else 0.0

            if silencio < BLOQUES_SILENCIO and config.UMBRAL_MANUAL is None:
                # Llego a los 8 s sin silencio: el ruido esta sobre el umbral
                anterior = self.umbral
                mediana = float(np.median(niveles_frase))
                self.umbral = min(UMBRAL_TECHO, max(anterior, FACTOR_FRASE_LARGA * mediana))
                print("  (frase de 8 s: umbral {:.0f} -> {:.0f}; mediana de la frase {:.0f})".format(
                    anterior, self.umbral, mediana))

            seg_voz = (ultimo - inicio + 1) * SEG_BLOQUE
            if seg_voz < SEG_VOZ_MINIMA:
                print("  (sonido corto de {:.2f} s, lo ignoro)".format(seg_voz))
                previos.clear()
                frase = None
                continue

            self.vaciar()
            audio = np.concatenate(frase)
            audio -= audio.mean()                    # quita el desnivel de continua
            return audio / 32768.0, seg_voz, t_ultima_voz
