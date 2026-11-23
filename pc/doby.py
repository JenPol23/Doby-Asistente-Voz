"""
doby.py  -  CORRE EN EL PC
Asistente Doby: maquina de estados (DORMIDO / DESPIERTO), aparatos y respuestas.
La intencion la decide el modelo entrenado (pc/nlu.py), cargado desde disco.
Doby habla por el parlante de la ESP32 y acciona sus reles.

Uso (desde la carpeta del proyecto):
  py pc/doby.py           -> modo voz: microfono de la ESP32 + Whisper
  py pc/doby.py --texto   -> las frases se escriben en vez de decirse
                              (Doby igual habla por la ESP32 y mueve los reles)
"""

import argparse
import random
import time
from difflib import SequenceMatcher

import numpy as np

import config
import hora
import tts
from esp32_cliente import Esp32Cliente
from nlu import Nlu
from texto import normalizar

UMBRAL = 0.5            # confianza minima del modelo

# Palabra de activacion (sobre texto normalizado)
VARIANTES_DOBY = {"doby", "dobby", "dobi", "dobbi", "dobie", "dobbie", "dovi"}
PARECIDO_DOBY = 0.75    # SequenceMatcher para palabras de 4+ letras
PALABRAS_SALUDO = {"hola", "oye", "hey"}
MAX_PALABRAS_LLAMADO = 4    # llamado relajado: solo en frases cortas
PARECIDO_LLAMADO = 0.6      # llamado relajado: parecido minimo con "doby"
EXACTAS_LLAMADO = {"doli", "doly", "doi"}  # llamado relajado: transcripciones vistas en los ensayos

SEG_DESCARTE = 0.3          # microfono que se bota despues de que Doby habla
                            # (~ el bufer I2S de la ESP32; el OK llega al terminar el sonido)
SEG_RECALIBRAR = 1.0        # si se movio un rele: se escucha 1 s y se rehace el umbral

# Eco del parlante (solo con verificacion de hablante y Doby dormido): una frase que EMPIEZA hasta
# 3 s despues de que Doby termino de hablar y cuyas palabras son lo que Doby acaba de decir se ignora.
VENTANA_ECO = 3.0           # s; fuera de la ventana nunca se ignora nada
PARECIDO_ECO = 0.6          # SequenceMatcher contra la ultima frase de Doby
PALABRAS_LLAMADO = {"hola", "ola", "oye", "hey", "doby"}

# "Prende todo": verbo de encender + una de estas palabras, sin aparato nombrado -> todos los aparatos
TODO = {"todo", "todos", "todas"}
# Respuesta a "¿Cual quieres que encienda/apague?": vale para la frase siguiente si EMPIEZA a lo mas
# SEG_PREGUNTA s despues de la pregunta y solo nombra aparatos (o "todo") con palabras de RELLENO
SEG_PREGUNTA = 8.0
RELLENO = {"el", "la", "los", "las", "lo", "y", "e", "a", "al", "del", "de", "tambien", "porfa", "por",
           "favor", "ahora", "mejor", "eh", "pues", "pelo", "cabello"}    # "la plancha del pelo"

# Sinonimos -> aparato (se comparan palabras completas). caudin, cautina, alizadora y lizadora: lo que
# transcribio Whisper en la prueba del cambio de aparatos (resultados/whisper_aparatos.csv)
SINONIMOS = {
    "bombillo": "bombillo", "bombilla": "bombillo", "luz": "bombillo",
    "luces": "bombillo", "foco": "bombillo",
    "ventilador": "ventilador", "abanico": "ventilador",
    "cautin": "cautin", "soldador": "cautin", "caudin": "cautin", "cautina": "cautin",
    "plancha": "plancha", "planchita": "plancha", "alisadora": "plancha", "alizadora": "plancha",
    "lizadora": "plancha",
}

# "Encender el ultimo mencionado" con un aparato caliente (config.CALIENTES): solo si la frase no trae
# otra palabra que pueda ser un aparato ("prende el carro" -> se pregunta "¿Cual quieres que encienda?").
# Se aceptan verbos (VERBOS), RELLENO y estas palabras; cualquier otra cuenta como sustantivo.
SIN_SUSTANTIVO = RELLENO | {"ya", "dale", "mira", "oye", "otra", "vez", "nuevo", "me", "te", "se", "que",
                            "puedes", "podrias", "quiero", "vuelve", "volver", "si", "no"}
# "¿Que hora es?": tras quitar "doby" y el saludo debe quedar EXACTAMENTE "que hora es", con a lo mas estas
# palabras de cortesia ("a que hora es la funcion" o "que hora es en madrid" siguen yendo al modelo)
CORTESIA = {"por", "favor", "porfa", "mira", "oye", "dime", "ahora", "ya"}
SEG_REINTENTO_AUTO = 5.0    # apagado automatico: si la ESP32 no confirma, se reintenta cada 5 s
INTENTOS_SALIDA = 3         # al cerrar Doby: intentos de apagar el cautin y la plancha

# Raices implicitas: raiz -> (aparato, intencion). Se compara el INICIO de cada palabra.
RAICES_IMPLICITAS = {
    "calor": ("ventilador", "encender"),
    "frio": ("ventilador", "apagar"),
    "oscur": ("bombillo", "encender"),
}

# Raices de verbos por intencion (para el respaldo implicito, inicio de palabra)
VERBOS = {
    "encender": ["prend", "encend", "enciend", "activ"],
    "apagar": ["apag", "desactiv", "deten", "fren"],
    "descansar": ["descans", "dorm"],
    "agradecer": ["gracias"],
}


# ---------------- Funciones de texto ----------------
def es_doby(palabra):
    """True si la palabra es 'doby' o se le parece lo suficiente."""
    if palabra in VARIANTES_DOBY:
        return True
    return len(palabra) >= 4 and SequenceMatcher(None, palabra, "doby").ratio() >= PARECIDO_DOBY


def llamado_corto(palabras):
    """
    Llamado relajado para frases de 4 palabras o menos: 'hola'/'ola'/'o la'
    seguido de una palabra parecida a 'doby' (>= 0.6, sin minimo de letras)
    o de 'doli'/'doly', por ejemplo 'ola dobi', 'hola dolly' u 'hola doli'. Devuelve las palabras que quedan, o None si no aplica.
    """
    if len(palabras) > MAX_PALABRAS_LLAMADO:
        return None
    if palabras[:1] in (["hola"], ["ola"]):
        i = 1
    elif palabras[:2] == ["o", "la"]:
        i = 2
    else:
        return None
    if i < len(palabras) and (palabras[i] in EXACTAS_LLAMADO or
                              SequenceMatcher(None, palabras[i], "doby").ratio() >= PARECIDO_LLAMADO):
        return palabras[i + 1:]
    return None


def empieza_con_llamado(palabras):
    """'hola doby ...' u 'ola dobi ...' al INICIO de la frase (no basta con que aparezca 'doby')."""
    return llamado_corto(palabras) is not None or (
        len(palabras) >= 2 and palabras[0] in PALABRAS_SALUDO and es_doby(palabras[1]))


def empieza_con(palabras, raices):
    """True si alguna palabra EMPIEZA con alguna de las raices."""
    return any(p.startswith(r) for p in palabras for r in raices)


def intencion_por_verbo(palabras):
    """
    Respaldo cuando el modelo no supera el umbral: verbo explicito de encender o
    de apagar + al menos un aparato por sinonimo. Si hay verbos de los dos, no aplica.
    """
    if not any(p in SINONIMOS for p in palabras):
        return None
    hay_encender = empieza_con(palabras, VERBOS["encender"])
    hay_apagar = empieza_con(palabras, VERBOS["apagar"])
    if hay_encender and not hay_apagar:
        return "encender"
    if hay_apagar and not hay_encender:
        return "apagar"
    return None


def intencion_implicita(palabras):
    """
    Respaldo cuando el modelo no supera el umbral: 'calor'/'oscur' -> encender,
    'frio' -> apagar, siempre que no aparezca un verbo de OTRA intencion.
    """
    for raiz, (_, intencion) in RAICES_IMPLICITAS.items():
        if empieza_con(palabras, [raiz]):
            otros = [v for i, raices in VERBOS.items() if i != intencion for v in raices]
            if empieza_con(palabras, otros):
                return None
            return intencion
    return None


def buscar_aparatos(palabras):
    """Devuelve (aparatos, origen): primero sinonimos, luego raices implicitas."""
    mencionados = {SINONIMOS[p] for p in palabras if p in SINONIMOS}
    if mencionados:
        return [a for a in config.APARATOS if a in mencionados], "mencionado"
    for raiz, (aparato, _) in RAICES_IMPLICITAS.items():
        if empieza_con(palabras, [raiz]):
            return [aparato], "implicito ('{}')".format(raiz)
    return [], None


def trae_sustantivo(palabras):
    """
    True si queda alguna palabra que no es verbo de encender/apagar ni de SIN_SUSTANTIVO:
    'prende el carro' -> True; 'préndela','ya préndela por favor', 'vuelve a prenderla' -> False.
    """
    verbos = VERBOS["encender"] + VERBOS["apagar"]
    return any(p not in SIN_SUSTANTIVO and not any(p.startswith(v) for v in verbos) for p in palabras)


def es_que_hora(palabras):
    """'que hora es', 'que hora es por favor', 'mira que hora es' -> True; 'a que hora es la funcion' -> False."""
    return [p for p in palabras if p not in CORTESIA] == ["que", "hora", "es"]


def es_encender_todo(palabras):
    """
    'prende todo', 'enciende todos', 'activa todo': verbo de encender + todo/todos/todas, sin verbo
    de apagar ('apaga todo' sigue siendo apagar_todo) y sin aparato nombrado ('prende todas las
    luces' es solo el bombillo).
    """
    return (any(p in TODO for p in palabras) and empieza_con(palabras, VERBOS["encender"])
            and not empieza_con(palabras, VERBOS["apagar"]) and not buscar_aparatos(palabras)[0])


def respuesta_a_pregunta(palabras):
    """
    'el ventilador', 'el bombillo y la plancha' -> 'aparatos'; 'todo' / 'todos' -> 'todo'; cualquier
    otra frase (con un verbo, un saludo, etc.) -> None: es una orden nueva.
    """
    if not palabras or any(p not in SINONIMOS and p not in TODO and p not in RELLENO for p in palabras):
        return None
    if any(p in SINONIMOS for p in palabras):
        return "aparatos"
    return "todo" if any(p in TODO for p in palabras) else None


# ---------------- Doby ----------------
class Doby:
    def __init__(self, esp, nlu, verificador=None):
        self.esp = esp
        self.nlu = nlu
        self.verificador = verificador  # None = sin verificacion de hablante (como antes)
        self.persona_activa = None      # quien desperto a Doby (para la voz clonada)
        self.despierto = False
        self.encendidos = set()     # aparatos encendidos (la ESP32 arranco con TODOS 0)
        self.ultimos = []           # ultimo(s) aparato(s) mencionado(s), para "apagalo"
        self.inicio_respuesta = None  # hora del primer decir() de la frase (modo voz)
        self.movio_reles = False      # True si en la frase se acciono algun rele (modo voz)
        self.ultima_dicha = None      # ultima frase de Doby y cuando termino de sonar (OK de la ESP32)
        self.fin_habla = None
        self.inicio_voz = None        # cuando empezo la voz de la frase actual (modo voz)
        self.pregunta = None          # ("encender" | "apagar", instante) tras "¿Cual quieres que...?"
        self.encendido_desde = {}     # aparato caliente encendido -> instante en que se encendio
        self.reintento_auto = 0.0     # apagado automatico: no reintentar antes de este instante

    def decir(self, clave, con_persona=True):
        """con_persona=False: la frase no es para la persona verificada (no reconozco / repite)."""
        if self.inicio_respuesta is None:
            self.inicio_respuesta = time.perf_counter()
        pcm, texto, voz = self.voz_de(clave, con_persona)
        self.sonar(pcm, texto, voz, clave)

    def decir_hora(self):
        """La hora del reloj del PC (America/Bogota) como frase entera pregenerada (pc/hora.py)."""
        if self.inicio_respuesta is None:
            self.inicio_respuesta = time.perf_counter()
        ahora = hora.ahora()
        pcm, texto, voz = self.voz_hora(ahora.hour, ahora.minute)
        self.sonar(pcm, texto, voz, hora.clave(ahora.hour, ahora.minute))

    def voz_hora(self, h, m):
        """(pcm, texto, voz). Con VOZ_CLONADA: persona verificada (o VOZ_POR_DEFECTO) -> su frase; si le falta, la
        hora COMPLETA con la voz normal y queda en el log (voz_clonada.obtener_hora). Sin VOZ_CLONADA: la voz
        normal desde voz_cache/hora/. Nunca se genera voz."""
        if config.VOZ_CLONADA:
            import voz_clonada
            return voz_clonada.obtener_hora(self.persona_activa or config.VOZ_POR_DEFECTO, h, m)
        pcm = hora.leer(hora.ruta_normal(h, m))
        return (pcm, hora.texto(h, m), None) if pcm is not None else (np.zeros(0, dtype=np.int16), "", None)

    def sonar(self, pcm, texto, voz, clave):
        """Envia el audio a la ESP32 y recuerda lo dicho (para es_eco). Con pcm vacio no envia nada."""
        if len(pcm) == 0:                       # faltan el audio y sus respaldos (nunca se genera en vivo)
            print("  (Doby no dice nada: falta el audio de '{}')".format(clave))
            return
        print('  Doby{}: "{}"'.format(" [voz de {}]".format(voz) if voz else "", texto))
        if not self.esp.hablar(pcm):
            print("  AVISO: la ESP32 no confirmo el audio.")
        self.ultima_dicha, self.fin_habla = texto, time.perf_counter()   # texto real (para es_eco)

    def voz_de(self, clave, con_persona=True):
        """(pcm, texto, voz). Con VOZ_CLONADA: persona verificada -> su voz clonada (sus respaldos, nunca
        otra voz); sin persona (o con_persona=False) -> VOZ_POR_DEFECTO o la voz normal SOLO desde los WAV
        de voz_cache/ (nunca gTTS). Con VOZ_CLONADA = False: gTTS, como antes."""
        if config.VOZ_CLONADA:
            import voz_clonada
            voz = (self.persona_activa if con_persona else None) or config.VOZ_POR_DEFECTO
            if voz:
                pcm, texto, _ = voz_clonada.obtener_seguro(voz, clave)   # los respaldos se registran alli
                return pcm, texto, voz
            pcm, texto = voz_clonada.normal(clave)
            return pcm, texto, None
        return tts.obtener(clave), tts.FRASES[clave], None

    def dormir(self):
        self.despierto = False
        self.persona_activa = None
        self.pregunta = None
        print("  -> Doby se durmio. Di 'Hola Doby' para despertarlo.")

    def mostrar_estado(self):
        encendidos = [a for a in config.APARATOS if a in self.encendidos]
        print("  [{}] encendidos: {}".format(
            "DESPIERTO" if self.despierto else "DORMIDO",
            ", ".join(encendidos) if encendidos else "ninguno"))

    # ---------- Entender la frase ----------
    def procesar(self, frase, audio=None):
        palabras = normalizar(frase).split()
        relajado = llamado_corto(palabras)
        hay_doby = relajado is not None or any(es_doby(p) for p in palabras)

        if not self.despierto and not hay_doby:
            print("  (dormido: no escuche 'doby', ignoro la frase)")
            if self.verificador is not None and not self.es_eco(frase):
                self.verificador.cancelar()     # no fue el segundo "Hola Doby" (un eco no cancela)
            return

        if not self.verificar_hablante(frase, audio, empieza_con_llamado(palabras)):
            return

        quito_saludo = False
        if relajado is not None:
            print("  Llamado relajado: '{}'".format(" ".join(palabras[:len(palabras) - len(relajado)])))
            palabras = relajado
            quito_saludo = True
            if not self.despierto:
                self.despierto = True
                print("  -> Doby desperto.")
        elif hay_doby:
            restantes = []
            for p in palabras:
                if es_doby(p):
                    continue
                if p in PALABRAS_SALUDO:
                    quito_saludo = True
                    continue
                restantes.append(p)
            palabras = restantes
            if not self.despierto:
                self.despierto = True
                print("  -> Doby desperto.")

        pregunta, self.pregunta = self.pregunta, None        # la pregunta solo vale para esta frase
        respuesta = respuesta_a_pregunta(palabras) if self.pregunta_vigente(pregunta) else None
        if not palabras:
            intencion = "saludo"
            print("  Solo el llamado a Doby -> saludo")
        elif respuesta == "aparatos":
            intencion = pregunta[0]
            print("  Respuesta a '¿Cual quieres que {}?': {}".format(
                "encienda" if intencion == "encender" else "apague", " ".join(palabras)))
        elif respuesta == "todo":
            intencion = "encender_todo" if pregunta[0] == "encender" else "apagar_todo"
            print("  Respuesta a la pregunta: todo -> {}".format(intencion))
        elif es_encender_todo(palabras):
            intencion = "encender_todo"
            print("  '{}' -> encender todo".format(" ".join(palabras)))
        elif es_que_hora(palabras):
            intencion = "hora"
            print("  '{}' -> la hora".format(" ".join(palabras)))
        else:
            texto = " ".join(palabras)
            intencion, confianza = self.nlu.clasificar(texto)
            print("  Modelo: '{}' -> {} (confianza {:.2f})".format(texto, intencion, confianza))
            if confianza < UMBRAL:
                por_verbo = intencion_por_verbo(palabras)
                implicita = intencion_implicita(palabras)
                if por_verbo:
                    intencion = por_verbo
                    print("  Confianza < {} -> respaldo verbo + aparato: {}".format(UMBRAL, intencion))
                elif implicita:
                    intencion = implicita
                    print("  Confianza < {} -> respaldo implicito: {}".format(UMBRAL, intencion))
                elif quito_saludo:
                    intencion = "saludo"
                    print("  Confianza < {} y venia un saludo -> saludo".format(UMBRAL))
                else:
                    intencion = None
                    print("  Confianza < {} -> no entendi".format(UMBRAL))

        self.ejecutar(intencion, palabras)
        self.mostrar_estado()

    def pregunta_vigente(self, pregunta):
        """La frase EMPEZO a lo mas SEG_PREGUNTA s despues de la pregunta (en modo texto: al procesarla)."""
        if pregunta is None:
            return False
        ahora = self.inicio_voz if self.inicio_voz is not None else time.perf_counter()
        return ahora - pregunta[1] <= SEG_PREGUNTA

    # ---------- Verificacion de hablante ----------
    def verificar_hablante(self, frase, audio, saludo=False):
        """
        True si la frase sigue. Sin verificador o sin audio (modo texto): siempre True.
        Dormido: regla del llamado (umbral alto + zona gris). Despierto con VERIFICAR_ORDENES:
        regla de sesion (config.UMBRAL_SESION, solo persona_activa); si la frase EMPIEZA con
        "Hola Doby", regla del llamado y, si se acepta, puede cambiar persona_activa.
        """
        if self.verificador is None or audio is None:
            return True
        if self.es_eco(frase):                  # Whisper transcribio lo que Doby acaba de decir
            print("  (parece el eco de lo que acaba de decir Doby: ignoro la frase)")
            return False                        # sin verificar y sin tocar el intento pendiente
        llamado = not self.despierto or (saludo and config.VERIFICAR_ORDENES)
        if not llamado and not config.VERIFICAR_ORDENES:
            return True
        r = self.verificador.verificar(audio, frase, "llamado" if llamado else "orden",
                                       persona_activa=None if llamado else self.persona_activa)
        if r["estado"] == "aceptado":
            if self.persona_activa and r["nombre"] != self.persona_activa:
                print("  -> Cambia la persona activa: {} -> {}".format(self.persona_activa, r["nombre"]))
            self.persona_activa = r["nombre"]
            print("  -> Hablante verificado: {}".format(r["nombre"]))
            return True
        if r["estado"] == "repetir":            # solo en el llamado; en ordenes cuenta como desconocido
            self.decir("repite_hola", con_persona=False)    # no se sabe quien hablo: sin voz clonada
        elif r.get("sin_voz") and self.despierto and self.persona_activa:
            print("  (audio demasiado corto para verificar: no ejecuto nada y pido repetir)")
            self.decir("no_entendi")            # con la voz de persona_activa: no fue un rechazo de voz
        elif config.MODO_RECHAZO == "avisar":
            self.decir("no_reconozco", con_persona=False)
        else:
            print("  (MODO_RECHAZO = silencio: ignoro la frase)")
        return False

    def es_eco(self, frase):
        """
        True si la frase parece el eco de lo ultimo que dijo Doby. Solo con Doby DORMIDO (llamado):
        despierto, sus respuestas repiten las palabras de las ordenes ("Listo, encendi el ventilador")
        y una orden real se confundiria con eco. Condiciones: la voz EMPEZO a lo mas VENTANA_ECO s
        despues de que Doby termino de hablar, y las PALABRAS se parecen a esa frase (>= 0.6) o son
        un trozo seguido de ella con alguna palabra que no sea del llamado.
        Un "Hola Doby" a secas nunca es eco por texto: no se distingue de un llamado real.
        """
        if self.despierto or self.ultima_dicha is None or self.fin_habla is None or self.inicio_voz is None:
            return False
        if not -0.5 <= self.inicio_voz - self.fin_habla <= VENTANA_ECO:
            return False
        dicho = ["doby" if es_doby(p) else p for p in normalizar(self.ultima_dicha).split()]
        oido = ["doby" if es_doby(p) else p for p in normalizar(frase).split()]
        if not oido:
            return False
        if SequenceMatcher(None, oido, dicho).ratio() >= PARECIDO_ECO:     # por palabras, no por letras
            return True
        trozo = len(oido) >= 2 and any(dicho[i:i + len(oido)] == oido for i in range(len(dicho) - len(oido) + 1))
        return trozo and any(p not in PALABRAS_LLAMADO for p in oido)

    # ---------- Actuar y responder ----------
    def ejecutar(self, intencion, palabras):
        if intencion in ("encender", "apagar"):
            self.accionar(intencion == "encender", palabras)
        elif intencion == "encender_todo":
            self.encender_todo()
        elif intencion == "apagar_todo":
            if self.esp.todos_apagados():
                self.movio_reles = True
                self.encendidos.clear()
                self.encendido_desde.clear()
                print("  Reles: TODOS 0")
            else:
                print("  AVISO: la ESP32 no confirmo TODOS 0.")
            self.decir("apagar_todo")
            self.dormir()
        elif intencion == "descansar":
            self.decir("descansar")
            self.dormir()
        elif intencion == "consultar_estado":
            self.decir(tts.clave_estado(self.encendidos))
        elif intencion == "saludo":
            self.decir(random.choice(["saludo_1", "saludo_2"]))
        elif intencion == "agradecer":
            self.decir("agradecer")
        elif intencion == "hora":
            self.decir_hora()
        else:                                   # fuera_de_dominio o baja confianza
            self.decir("no_entendi")

    def accionar(self, encender, palabras):
        aparatos, origen = buscar_aparatos(palabras)
        if not aparatos and self.ultimos:
            if encender and any(a in config.CALIENTES for a in self.ultimos) and trae_sustantivo(palabras):
                print("  (el ultimo mencionado incluye un aparato caliente y la frase nombra otra cosa: pregunto)")
            else:
                aparatos, origen = self.ultimos, "el ultimo mencionado"
        if not aparatos:
            self.decir("cual_encender" if encender else "cual_apagar")
            self.pregunta = ("encender" if encender else "apagar", time.perf_counter())   # despues de que sono
            return

        print("  Aparato(s): {} ({})".format(", ".join(aparatos), origen))
        self.ultimos = aparatos
        varios = len(aparatos) > 1          # varios: una sola frase al final con el estado
        for aparato in aparatos:
            k = config.APARATOS[aparato]
            if encender and aparato in self.encendidos:
                frase = "ya_encendido_" + aparato
            elif not encender and aparato not in self.encendidos:
                frase = "ya_apagado_" + aparato
            elif self.esp.rele(k, encender):
                self.movio_reles = True
                print("  Rele {} ({}) -> {}".format(k, aparato, "ENCENDIDO" if encender else "APAGADO"))
                if encender:
                    self.encendidos.add(aparato)
                else:
                    self.encendidos.discard(aparato)
                self.marcar_caliente(aparato, encender)
                frase = ("encendi_" if encender else "apague_") + aparato
            else:
                print("  AVISO: la ESP32 respondio ERR al rele {}.".format(k))
                continue
            if varios:
                print("  ({})".format(frase))
            else:
                self.decir(frase)
        if varios:          # "Todo está apagado." o el estado que corresponda (frases ya clonadas)
            self.decir(tts.clave_estado(self.encendidos))

    def encender_todo(self):
        """Enciende los aparatos que falten (los encendidos se quedan) y responde con la frase de estado,
        que ya existe clonada: con los cuatro, "Estan encendidos el bombillo, el ventilador, el cautin y
        la plancha." Si un rele responde ERR, la frase dice lo que de verdad quedo encendido."""
        for aparato, k in config.APARATOS.items():
            if aparato in self.encendidos:
                continue
            if self.esp.rele(k, True):
                self.movio_reles = True
                self.encendidos.add(aparato)
                self.marcar_caliente(aparato, True)
                print("  Rele {} ({}) -> ENCENDIDO".format(k, aparato))
            else:
                print("  AVISO: la ESP32 respondio ERR al rele {}.".format(k))
        self.ultimos = list(config.APARATOS)        # "apagalo" despues de "prende todo": todos
        self.decir(tts.clave_estado(self.encendidos))

    # ---------- Apagado automatico de los aparatos calientes ----------
    def marcar_caliente(self, aparato, encendido):
        """Lleva la hora de encendido del cautin y la plancha. Pedir 'prende' otra vez no la reinicia."""
        if aparato not in config.CALIENTES:
            return
        if encendido:
            self.encendido_desde.setdefault(aparato, time.perf_counter())
        else:
            self.encendido_desde.pop(aparato, None)

    def vencidos(self):
        """Aparatos calientes encendidos hace APAGADO_AUTOMATICO minutos o mas (None: nunca)."""
        if not config.APAGADO_AUTOMATICO or not self.encendido_desde:
            return []
        ahora = time.perf_counter()
        if ahora < self.reintento_auto:
            return []
        limite = config.APAGADO_AUTOMATICO * 60
        return [a for a in config.APARATOS if a in self.encendido_desde and ahora - self.encendido_desde[a] >= limite]

    def apagado_automatico(self):
        """Apaga los vencidos y lo avisa ("Por seguridad, apague el cautin."). True si uso la ESP32.
        Con persona_activa, con su voz; dormido, con la voz normal (como cualquier frase de Doby)."""
        vencidos = self.vencidos()
        for aparato in vencidos:
            k = config.APARATOS[aparato]
            if self.esp.rele(k, False):
                self.movio_reles = True
                self.encendidos.discard(aparato)
                self.encendido_desde.pop(aparato, None)
                print("  APAGADO AUTOMATICO: rele {} ({}) tras {} min encendido".format(
                    k, aparato, config.APAGADO_AUTOMATICO))
                self.decir("auto_apagado_" + aparato)
            else:
                print("  AVISO: la ESP32 no confirmo el apagado automatico del rele {} ({}); reintento en {:.0f} s."
                      .format(k, aparato, SEG_REINTENTO_AUTO))
                self.reintento_auto = time.perf_counter() + SEG_REINTENTO_AUTO
        if vencidos:
            self.mostrar_estado()
        return bool(vencidos)


# ---------------- Programa principal ----------------
def main():
    parser = argparse.ArgumentParser(description="Asistente de voz Doby")
    parser.add_argument("--texto", action="store_true",
                        help="escribir las frases en vez de decirlas")
    args = parser.parse_args()

    preparar_voz()
    print("\n2. Modelo de intenciones:")
    nlu = Nlu()
    if not args.texto:
        print("\n3. Whisper (voz a texto):")
        from stt import Stt                    # solo en modo voz (importa torch)
        stt = Stt()
    verificador = None
    if config.VERIFICAR_HABLANTE:
        if args.texto:
            print("\n(Verificacion de hablante: solo en modo voz; en modo texto no aplica.)")
        else:
            print("\n3b. Verificacion de hablante (ECAPA):")
            verificador = cargar_verificador()
    print("\n{}. ESP32:".format(3 if args.texto else 4))
    esp = Esp32Cliente()
    esp.conectar()
    esp.todos_apagados()
    print("Reles apagados al arrancar (TODOS 0).")

    doby = Doby(esp, nlu, verificador)
    try:
        if args.texto:
            modo_texto(doby)
        else:
            modo_voz(doby, esp, stt)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        apagar_calientes_al_salir(esp)
        print("Doby terminado. Los demas reles quedan como estaban.")


def apagar_calientes_al_salir(esp):
    """
    Al cerrar Doby (normal, Ctrl+C o error): RELE k 0 del cautin y la plancha por una conexion NUEVA (en
    la vieja puede haber respuestas MIC pendientes) y con intentos limitados (conectar() normal reintenta
    para siempre). Ctrl+C no lo interrumpe. Si no se logra, la ESP32 los apaga sola al quedarse sin PC.
    Usa Esp32Cliente._orden_linea() (privado), igual que entrenamiento/grabar_ruido.py.
    """
    reles = [config.APARATOS[a] for a in config.CALIENTES]
    for intento in range(1, INTENTOS_SALIDA + 1):
        try:
            if esp.conectar(intentos=1) and all(esp._orden_linea("RELE {} 0".format(k)) == "OK" for k in reles):
                esp.cerrar()
                print("Apagados al salir: {} (reles {}).".format(
                    " y ".join(config.CALIENTES), ", ".join(map(str, reles))))
                return True
        except KeyboardInterrupt:
            print("  (Ctrl+C ignorado: primero hay que apagar el cautin y la plancha)")
        except (OSError, ConnectionError, UnicodeDecodeError):
            pass
        print("  No se pudo confirmar el apagado del cautin y la plancha (intento {}/{}).".format(intento, INTENTOS_SALIDA))
    esp.cerrar()
    print("!!! NO SE PUDO CONFIRMAR EL APAGADO del cautin y la plancha: la ESP32 los apagara sola sin PC. !!!")
    return False


def preparar_voz():
    """Sin VOZ_CLONADA: pregenera voz_cache/ con gTTS (como antes). Con VOZ_CLONADA: nunca gTTS; se
    comprueba que no falte ningun audio y, si falta, se avisa claro (Doby sigue con sus respaldos)."""
    if not config.VOZ_CLONADA:
        print("1. Voz de Doby (voz_cache/):")
        tts.pregenerar()
        return True
    import voz_clonada
    print("1. Voz de Doby: clonada ({}) + voz normal solo desde voz_cache/ (sin gTTS)".format(config.CARPETA_VOZ_CLONADA))
    try:
        ok, lineas = voz_clonada.cobertura()
    except Exception as e:                      # p. ej. falta hablantes.json
        ok, lineas = False, ["  no se pudo comprobar la cobertura: {}".format(e)]
    print("\n".join(lineas))
    if not ok:
        print("\n" + "!" * 70 + "\n!!  ERROR: FALTAN AUDIOS DE VOZ. Corre: py pruebas/verificar_cobertura.py\n"
              "!!  Doby sigue, pero esas frases sonaran con un respaldo o en silencio.\n" + "!" * 70)
    return ok


def cargar_verificador():
    """Carga la verificacion de hablante; si algo falla, Doby sigue SIN verificacion."""
    try:
        from verificador import Verificador    # importa entrenamiento/hablantes.py (speechbrain)
        return Verificador()
    except Exception as e:
        print("  AVISO: no se pudo cargar la verificacion de hablante ({}). "
              "Doby sigue SIN verificacion.".format(e))
        return None


def modo_texto(doby):
    print("\nModo texto. Escribe lo que le dirias a Doby (linea vacia o 'salir' para terminar).")
    doby.mostrar_estado()
    while True:
        frase = input("\n> ").strip()
        doby.apagado_automatico()          # en modo texto solo se revisa al escribir (input() bloquea)
        if not frase or frase.lower() == "salir":
            break
        doby.procesar(frase)


def modo_voz(doby, esp, stt):
    from entrada_audio import EntradaAudio, normalizar_volumen
    entrada = EntradaAudio(esp)
    print("\n5. Calibrando 2 s de ruido: NO hables y deja todo apagado...")
    entrada.calibrar()

    def al_esperar():
        """Mientras no hay voz: apagado automatico de los aparatos calientes, con el socket libre."""
        if not doby.vencidos():
            return False
        entrada.vaciar()                       # sin MIC pendientes: RELE y HABLAR van solos
        doby.apagado_automatico()
        entrada.descartar(SEG_DESCARTE)        # que Doby no se escuche a si mismo
        print("\nEscuchando...")
        return True

    print('\nModo voz (Ctrl+C para terminar). Doby esta DORMIDO. Di "Hola Doby" para despertarlo.')
    doby.mostrar_estado()
    while True:
        print("\nEscuchando...")
        crudo, seg_voz, fin_voz = entrada.escuchar_frase(al_esperar)   # crudo: lo que se verifica
        audio, ganancia = normalizar_volumen(crudo)          # (devuelve una copia: crudo no cambia)
        print("  Voz: nivel promedio {:.0f} (umbral {:.0f})   ganancia x{:.1f}".format(
            entrada.nivel_voz, entrada.umbral_frase, ganancia))

        inicio = time.perf_counter()
        frase = stt.transcribir(audio)
        seg_whisper = time.perf_counter() - inicio
        print('  Whisper: "{}"  (voz {:.2f} s, Whisper {:.2f} s)'.format(
            frase if frase else "", seg_voz, seg_whisper))
        if not frase:
            print("  (Whisper no entendio nada)")
            continue

        doby.inicio_respuesta = None
        doby.movio_reles = False
        doby.inicio_voz = fin_voz - seg_voz     # para es_eco(): cuando empezo a sonar esta frase
        doby.procesar(frase, crudo)
        if doby.inicio_respuesta is None:
            print("  Tiempo total: {:.2f} s (sin respuesta)".format(time.perf_counter() - fin_voz))
            continue
        print("  Tiempo hasta la respuesta: {:.2f} s   Total: {:.2f} s".format(
            doby.inicio_respuesta - fin_voz, time.perf_counter() - fin_voz))
        if doby.movio_reles:
            entrada.recalibrar(SEG_RECALIBRAR) # cambio el ruido (ej. ventilador sonando)
        else:
            entrada.descartar(SEG_DESCARTE)    # una vez: que Doby no se escuche a si mismo


if __name__ == "__main__":
    main()
