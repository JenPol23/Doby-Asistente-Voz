"""
prueba_ordenes.py  -  CORRE EN EL PC, SIN ESP32
Pruebas de las ordenes de Doby con una ESP32 falsa (anota reles y audios) y el modelo de intenciones real
(pc/nlu.py). Las frases se dan como texto (lo que transcribiria Whisper) y el reloj de Doby es virtual.
  1. "prende todo" (los 4 aparatos), "apaga todo", "apagalo" despues de "prende todo"
  2. respuesta a "¿Cual quieres que encienda/apague?"
  3. ordenes con varios aparatos (una sola frase de estado)
  4. llamado "hola doi"
  5. audio demasiado corto para verificar
  6. encender, apagar, "ya estaba..." y estado de cada uno de los 4 aparatos, con genero y sinonimos
  7. seguridad: "el ultimo mencionado" con aparatos calientes y apagado automatico (config.APAGADO_AUTOMATICO)

Uso:  py pruebas/prueba_ordenes.py      (codigo de salida 1 si algun caso falla)
Frases: texto; un numero = segundos que pasan; "AUTO" = Doby revisa el apagado automatico (como hacen
modo_voz/modo_texto); ("err", {k}) = desde ahi el rele k responde ERR.
"""

import contextlib
import io
import os
import sys
import types
import wave

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "pc"))

import numpy as np    # noqa: E402

import config         # noqa: E402
import doby           # noqa: E402
import tts            # noqa: E402
from nlu import Nlu   # noqa: E402

TODOS = sorted(config.APARATOS)                    # bombillo, cautin, plancha, ventilador
RELE = {a: k for a, k in config.APARATOS.items()}
RELOJ = [1000.0]
doby.time = types.SimpleNamespace(perf_counter=lambda: RELOJ[0])
NOMBRE = {"bombillo": "el bombillo", "ventilador": "el ventilador", "cautin": "el cautín", "plancha": "la plancha"}
TODOS_ON = "estado_bombillo_ventilador_cautin_plancha"


class EspFalsa:
    def __init__(self, err=()):
        self.eventos, self.audios, self.err = [], [], set(err)

    def hablar(self, pcm):
        self.audios.append(np.asarray(pcm, dtype=np.int16).tobytes())
        return True

    def rele(self, k, estado):
        self.eventos.append(("rele", k, int(bool(estado))))
        return k not in self.err

    def todos_apagados(self):
        self.eventos.append(("todos0",))
        return True


class VerificadorFalso:
    def __init__(self, r):
        self.r = r

    def verificar(self, audio, texto, tipo, persona_activa=None):
        return dict(self.r)

    def cancelar(self):
        pass


def leer_wav(ruta):
    with wave.open(ruta) as w:
        return w.readframes(w.getnframes())


def correr(nlu, frases, encendidos=(), despierto=True, err=(), persona=None, verificador=None):
    """Devuelve (eventos, dichos, encendidos, despierto, esp). Con verificador (falso), cada frase lleva un
    audio de relleno para que Doby la verifique."""
    esp = EspFalsa(err)
    d = doby.Doby(esp, nlu, verificador)
    d.despierto, d.encendidos, d.persona_activa = despierto, set(encendidos), persona
    for a in encendidos:                       # como si se hubieran encendido ahora
        d.marcar_caliente(a, True)
    dichos = []
    original = d.decir
    d.decir = lambda clave, *a, **k: (dichos.append(clave), original(clave, *a, **k))
    for f in frases:
        if isinstance(f, (int, float)):
            RELOJ[0] += f
        elif isinstance(f, tuple) and f[0] == "err":
            esp.err = set(f[1])
        elif f == "AUTO":
            with contextlib.redirect_stdout(io.StringIO()):
                d.apagado_automatico()
        else:
            RELOJ[0] += 1.0
            with contextlib.redirect_stdout(io.StringIO()):
                d.procesar(f, None if verificador is None else np.zeros(16000, dtype=np.float32))
    return esp.eventos, dichos, sorted(d.encendidos), d.despierto, esp


def rel(*aparatos, estado=1):
    return [("rele", RELE[a], estado) for a in config.APARATOS if a in aparatos]


CASOS = [
    # (nombre, frases, encendidos antes, esperado: eventos, dichos, encendidos despues, despierto)
    ("1a prende todo (todo apagado): los 4", ["prende todo"], [], rel(*TODOS), [TODOS_ON], TODOS, True),
    ("1b enciende todo (ventilador encendido)", ["enciende todo"], ["ventilador"],
     rel("bombillo", "cautin", "plancha"), [TODOS_ON], TODOS, True),
    ("1c prende todos (todo encendido)", ["prende todos"], TODOS, [], [TODOS_ON], TODOS, True),
    ("1d por favor prende todo", ["por favor prende todo"], [], rel(*TODOS), [TODOS_ON], TODOS, True),
    ("1e porfa prende todo", ["porfa prende todo"], [], rel(*TODOS), [TODOS_ON], TODOS, True),
    ("1f enciende todos los aparatos", ["enciende todos los aparatos"], [], rel(*TODOS), [TODOS_ON], TODOS, True),
    ("1g activa todo", ["activa todo"], [], rel(*TODOS), [TODOS_ON], TODOS, True),
    ("1h hola doby prende todo (dormido)", ["hola doby prende todo"], [], rel(*TODOS), [TODOS_ON], TODOS, "dormido"),
    ("1i prende todas las luces = solo el bombillo", ["prende todas las luces"], [], rel("bombillo"),
     ["encendi_bombillo"], ["bombillo"], True),
    ("1j apaga todo sigue igual", ["apaga todo"], TODOS, [("todos0",)], ["apagar_todo"], [], False),
    ("1k apagalo despues de prende todo = los 4", ["prende todo", "apagalo"], [], rel(*TODOS) + rel(*TODOS, estado=0),
     [TODOS_ON, "todo_apagado"], [], True),
    ("2a enciende... el ventilador", ["enciende el", "el ventilador"], [], rel("ventilador"),
     ["cual_encender", "encendi_ventilador"], ["ventilador"], True),
    ("2b apaga... el ventilador", ["apaga", "el ventilador"], ["ventilador"], rel("ventilador", estado=0),
     ["cual_apagar", "apague_ventilador"], [], True),
    ("2c enciende... el bombillo y la plancha", ["enciende", "el bombillo y la plancha"], [], rel("bombillo", "plancha"),
     ["cual_encender", "estado_bombillo_plancha"], ["bombillo", "plancha"], True),
    ("2d enciende... todo", ["enciende el", "todo"], [], rel(*TODOS), ["cual_encender", TODOS_ON], TODOS, True),
    ("2e expira: 15 s despues 'el ventilador' no se entiende", ["enciende el", 15, "el ventilador"], [], [],
     ["cual_encender", "no_entendi"], [], True),
    ("2f otra orden anula la pregunta", ["enciende el", "apaga el bombillo", "el ventilador"], [], [],
     ["cual_encender", "ya_apagado_bombillo", "no_entendi"], [], True),
    ("2g 'gracias' anula la pregunta", ["enciende el", "gracias", "el ventilador"], [], [],
     ["cual_encender", "agradecer", "no_entendi"], [], True),
    ("2h sin pregunta, 'el ventilador' sigue sin entenderse", ["el ventilador"], [], [], ["no_entendi"], [], True),
    ("2i 'el ventilador por favor' tambien vale", ["enciende el", "el ventilador por favor"], [], rel("ventilador"),
     ["cual_encender", "encendi_ventilador"], ["ventilador"], True),
    ("2j enciende... la plancha del pelo", ["enciende", "la plancha del pelo"], [], rel("plancha"),
     ["cual_encender", "encendi_plancha"], ["plancha"], True),
    ("2k apaga... el soldador", ["apaga", "el soldador"], ["cautin"], rel("cautin", estado=0),
     ["cual_apagar", "apague_cautin"], [], True),
    ("2l sin pregunta, 'el soldador' no enciende nada", ["el soldador"], [], [], ["no_entendi"], [], True),
    ("2m sin pregunta, 'la plancha' no enciende nada", ["la plancha"], [], [], ["no_entendi"], [], True),
    ("3a apaga los 4 (encendidos) -> 'Todo está apagado.'",
     ["apaga el bombillo, el ventilador, el cautín y la plancha"], TODOS, rel(*TODOS, estado=0), ["todo_apagado"], [], True),
    ("3b apaga dos de cuatro -> estado de los que quedan", ["apaga el bombillo y el cautín"], TODOS,
     rel("bombillo", "cautin", estado=0), ["estado_ventilador_plancha"], ["plancha", "ventilador"], True),
    ("3c enciende dos con los otros dos encendidos -> los 4", ["enciende el bombillo y la plancha"],
     ["ventilador", "cautin"], rel("bombillo", "plancha"), [TODOS_ON], TODOS, True),
    ("3d enciende dos (nada encendido)", ["enciende el bombillo y el cautín"], [], rel("bombillo", "cautin"),
     ["estado_bombillo_cautin"], ["bombillo", "cautin"], True),
    ("3e apaga dos que ya estaban apagados", ["apaga el bombillo y la plancha"], [], [], ["todo_apagado"], [], True),
    ("3f un solo aparato sigue igual", ["apaga el bombillo"], ["bombillo"], rel("bombillo", estado=0),
     ["apague_bombillo"], [], True),
    ("3h prende el cautin y la plancha", ["prende el cautín y la plancha"], [], rel("cautin", "plancha"),
     ["estado_cautin_plancha"], ["cautin", "plancha"], True),
    ("3i prende la plancha y el ventilador", ["prende la plancha y el ventilador"], [], rel("ventilador", "plancha"),
     ["estado_ventilador_plancha"], ["plancha", "ventilador"], True),
]

# 6. Cada aparato: encender, ya encendido, apagar, ya apagado, estado (con su genero)
for _a in config.APARATOS:
    _n = NOMBRE[_a]
    CASOS += [
        ("6 {}: prende {} (apagado)".format(_a, _n), ["prende " + _n], [], rel(_a), ["encendi_" + _a], [_a], True),
        ("6 {}: enciende {} (ya encendido)".format(_a, _n), ["enciende " + _n], [_a], [], ["ya_encendido_" + _a], [_a], True),
        ("6 {}: apaga {} (encendido)".format(_a, _n), ["apaga " + _n], [_a], rel(_a, estado=0), ["apague_" + _a], [], True),
        ("6 {}: apaga {} (ya apagado)".format(_a, _n), ["apaga " + _n], [], [], ["ya_apagado_" + _a], [], True),
        ("6 {}: ¿esta prendid{} {}? (encendido)".format(_a, tts._o(_a), _n),
         ["¿está prendid{} {}?".format(tts._o(_a), _n)], [_a], [], ["estado_" + _a], [_a], True),
        ("6 {}: prende {} y luego apagalo".format(_a, _n), ["prende " + _n, "apágalo"], [], rel(_a) + rel(_a, estado=0),
         ["encendi_" + _a, "apague_" + _a], [], True),
    ]
CASOS += [
    ("6 sinonimo: prende el soldador", ["prende el soldador"], [], rel("cautin"), ["encendi_cautin"], ["cautin"], True),
    ("6 sinonimo (Whisper): apaga el caudin", ["apaga el caudin"], ["cautin"], rel("cautin", estado=0),
     ["apague_cautin"], [], True),
    ("6 sinonimo (Whisper): prende la cautina", ["prende la cautina"], [], rel("cautin"), ["encendi_cautin"], ["cautin"], True),
    ("6 sinonimo: prende la planchita", ["prende la planchita"], [], rel("plancha"), ["encendi_plancha"], ["plancha"], True),
    ("6 sinonimo: apaga la alisadora", ["apaga la alisadora"], ["plancha"], rel("plancha", estado=0),
     ["apague_plancha"], [], True),
    ("6 sinonimo (Whisper): enciende la alizadora", ["enciende la alizadora"], [], rel("plancha"),
     ["encendi_plancha"], ["plancha"], True),
    ("6 sinonimo (Whisper): prende la lizadora", ["prende la lizadora"], [], rel("plancha"), ["encendi_plancha"],
     ["plancha"], True),
    ("6 sinonimo: apaga la plancha del pelo", ["apaga la plancha del pelo"], ["plancha"], rel("plancha", estado=0),
     ["apague_plancha"], [], True),
    ("6 ¿esta encendida la plancha? (nada encendido)", ["¿está encendida la plancha?"], [], [], ["todo_apagado"], [], True),
    ("6 ¿que esta encendido? (cautin y plancha)", ["¿qué está encendido?"], ["cautin", "plancha"], [],
     ["estado_cautin_plancha"], ["cautin", "plancha"], True),
    ("6 'prende el carro' (ya no existe, nada mencionado antes): pregunta", ["prende el carro"], [], [],
     ["cual_encender"], [], True),
]

# 7. Seguridad (config.APAGADO_AUTOMATICO = 10 min = 600 s; cada frase hace pasar 1 s)
CASOS += [
    ("7a ultimo mencionado caliente + otro sustantivo: pregunta y no enciende",
     ["prende la plancha", "apágala", "prende el carro"], [], rel("plancha") + rel("plancha", estado=0),
     ["encendi_plancha", "apague_plancha", "cual_encender"], [], True),
    ("7b ultimo mencionado caliente sin otro sustantivo: 'ya préndela por favor' la enciende",
     ["prende la plancha", "apágala", "ya préndela por favor"], [], rel("plancha") + rel("plancha", estado=0) + rel("plancha"),
     ["encendi_plancha", "apague_plancha", "encendi_plancha"], ["plancha"], True),
    ("7c apagar con otro sustantivo sigue usando el ultimo mencionado (apagar es seguro)",
     ["prende el cautín", "apaga el carro"], [], rel("cautin") + rel("cautin", estado=0),
     ["encendi_cautin", "apague_cautin"], [], True),
    ("7d ventilador (no caliente): 'prende el carro' usa el ultimo mencionado, como antes",
     ["prende el ventilador", "apágalo", "prende el carro"], [], rel("ventilador") + rel("ventilador", estado=0)
     + rel("ventilador"), ["encendi_ventilador", "apague_ventilador", "encendi_ventilador"], ["ventilador"], True),
    ("7e apagado automatico: a los 599 s nada, a los 600 s se apaga el cautin y lo avisa (ventilador sigue)",
     ["prende el cautín", "prende el ventilador", 598, "AUTO", 1, "AUTO"], [],
     rel("cautin") + rel("ventilador") + rel("cautin", estado=0),
     ["encendi_cautin", "encendi_ventilador", "auto_apagado_cautin"], ["ventilador"], True),
    ("7f pedir 'prende' otra vez no reinicia el tiempo",
     ["prende la plancha", 300, "prende la plancha", 299, "AUTO"], [], rel("plancha") + rel("plancha", estado=0),
     ["encendi_plancha", "ya_encendido_plancha", "auto_apagado_plancha"], [], True),
    ("7g apagar a mano y volver a prender reinicia el tiempo",
     ["prende el cautín", 300, "apaga el cautín", "prende el cautín", 590, "AUTO"], [],
     rel("cautin") + rel("cautin", estado=0) + rel("cautin"), ["encendi_cautin", "apague_cautin", "encendi_cautin"],
     ["cautin"], True),
    ("7h prende todo: a los 10 min se apagan el cautin y la plancha (bombillo y ventilador siguen)",
     ["prende todo", 600, "AUTO"], [], rel(*TODOS) + rel("cautin", "plancha", estado=0),
     [TODOS_ON, "auto_apagado_cautin", "auto_apagado_plancha"], ["bombillo", "ventilador"], True),
    ("7i apaga todo borra los tiempos", ["prende la plancha", "apaga todo", 700, "AUTO"], [],
     rel("plancha") + [("todos0",)], ["encendi_plancha", "apagar_todo"], [], False),
    ("7j la ESP32 responde ERR: reintenta a los 5 s",
     ["prende la plancha", 600, ("err", {RELE["plancha"]}), "AUTO", 4, "AUTO", ("err", set()), 1, "AUTO"], [],
     rel("plancha") + rel("plancha", estado=0) * 2, ["encendi_plancha", "auto_apagado_plancha"], [], True),
]


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        nlu = Nlu()
    config.VOZ_CLONADA = False
    config.APAGADO_AUTOMATICO = 10
    resultados = []
    for nombre, frases, antes, ev_esp, dichos_esp, enc_esp, desp in CASOS:
        dormido = desp == "dormido"
        ev, dichos, enc, despierto, _ = correr(nlu, frases, antes, despierto=not dormido)
        ok = ev == ev_esp and dichos == dichos_esp and enc == sorted(enc_esp) and despierto == (True if dormido else desp)
        resultados.append((nombre, ok, "" if ok else "   reles {} | dijo {} | encendidos {} | despierto {}".format(
            ev, dichos, enc, despierto)))

    # 1l: un rele responde ERR -> la frase dice lo que de verdad quedo encendido
    ev, dichos, enc, _, _ = correr(nlu, ["prende todo"], [], err={RELE["cautin"]})
    resultados.append(("1l rele del cautin con ERR: dice 'bombillo, ventilador y plancha'",
                       dichos == ["estado_bombillo_ventilador_plancha"] and enc == ["bombillo", "plancha", "ventilador"],
                       "   dijo {}".format(dichos)))

    # 3g: varios con un rele en ERR -> el estado dice lo que de verdad quedo encendido
    ev, dichos, enc, _, _ = correr(nlu, ["enciende el bombillo y el cautín"], [], err={RELE["cautin"]})
    resultados.append(("3g enciende dos, el cautin con ERR: dice 'Está encendido el bombillo.'",
                       dichos == ["estado_bombillo"] and enc == ["bombillo"], "   dijo {}".format(dichos)))

    # 7k: APAGADO_AUTOMATICO = None -> nunca se apaga solo
    config.APAGADO_AUTOMATICO = None
    ev, dichos, enc, _, _ = correr(nlu, ["prende el cautín", 10000, "AUTO"])
    resultados.append(("7k APAGADO_AUTOMATICO = None: nunca se apaga solo",
                       ev == rel("cautin") and enc == ["cautin"], "   reles {} | dijo {}".format(ev, dichos)))
    config.APAGADO_AUTOMATICO = 10

    # 4: llamado relajado con "doi"
    for frase, esperado in (("hola doi", True), ("hola, doi!", True), ("doi", False),
                            ("hola doi que tal como estas hoy", False)):
        _, dichos, _, despierto, _ = correr(nlu, [frase], despierto=False)
        resultados.append(("4 '{}' -> {}".format(frase, "despierta" if esperado else "no despierta"),
                           despierto == esperado, "   despierto {} | dijo {}".format(despierto, dichos)))

    # 1m / 6v / 7l: con VOZ_CLONADA las frases salen de voz_cache_f5/<persona>/
    import voz_clonada
    config.VOZ_CLONADA = True
    for p in voz_clonada.integrantes():
        _, _, _, _, esp = correr(nlu, ["prende todo"], persona=p)
        resultados.append(("1m voz clonada de {}: 'Están encendidos el bombillo, el ventilador, el cautín y la plancha.'"
                           .format(p), esp.audios == [leer_wav(voz_clonada.ruta(p, TODOS_ON))], ""))
        _, _, _, _, esp = correr(nlu, ["prende la plancha", "apágala", "apaga el cautín"], persona=p)
        esperado = [leer_wav(voz_clonada.ruta(p, c)) for c in ("encendi_plancha", "apague_plancha", "ya_apagado_cautin")]
        resultados.append(("6v voz clonada de {}: 'encendí la plancha', 'apagué la plancha', 'El cautín ya estaba apagado.'"
                           .format(p), esp.audios == esperado, ""))
        # 7l: aviso con la voz de quien esta activo; despues de 'descansa' (sin persona), con la voz normal
        _, dichos, _, _, esp = correr(nlu, ["prende el cautín", 600, "AUTO"], persona=p)
        resultados.append(("7l {} activo: el aviso del apagado automatico sale con su voz".format(p),
                           dichos[-1:] == ["auto_apagado_cautin"]
                           and esp.audios[-1] == leer_wav(voz_clonada.ruta(p, "auto_apagado_cautin")), ""))
    _, dichos, _, despierto, esp = correr(nlu, ["prende el cautín", "descansa", 599, "AUTO"], persona="jenpol")
    resultados.append(("7m Doby dormido (sin persona): el aviso sale con la voz normal",
                       not despierto and dichos[-1:] == ["auto_apagado_cautin"]
                       and esp.audios[-1] == leer_wav(tts._ruta("auto_apagado_cautin")), "   dijo {}".format(dichos)))

    # 5: audio demasiado corto para verificar (verificador falso con sin_voz)
    config.VERIFICAR_HABLANTE = config.VERIFICAR_ORDENES = True
    sin_voz = VerificadorFalso({"nombre": None, "mejor": "", "similitud": float("nan"), "estado": "desconocido",
                                "similitudes": {}, "sin_voz": True})
    otro = VerificadorFalso({"nombre": None, "mejor": "lina", "similitud": 0.2, "estado": "desconocido",
                             "similitudes": {}})
    normal_no_reconozco = leer_wav(tts._ruta("no_reconozco"))
    for p in voz_clonada.integrantes():
        ev, dichos, _, despierto, esp = correr(nlu, ["prende todo"], persona=p, verificador=sin_voz)
        resultados.append(("5a {} despierto, audio corto: 'No te entendí' con su voz y nada se mueve".format(p),
                           ev == [] and dichos == ["no_entendi"] and despierto
                           and esp.audios == [leer_wav(voz_clonada.ruta(p, "no_entendi"))],
                           "   reles {} | dijo {}".format(ev, dichos)))
    ev, dichos, _, despierto, esp = correr(nlu, ["hola doby"], despierto=False, verificador=sin_voz)
    resultados.append(("5b dormido, audio corto: igual que antes ('No reconozco tu voz.', voz normal)",
                       dichos == ["no_reconozco"] and esp.audios == [normal_no_reconozco] and not despierto,
                       "   dijo {}".format(dichos)))
    ev, dichos, _, _, esp = correr(nlu, ["prende todo"], persona="jenpol", verificador=otro)
    resultados.append(("5c despierto, voz de otra persona (no es audio corto): 'No reconozco tu voz.' con la voz normal",
                       ev == [] and dichos == ["no_reconozco"] and esp.audios == [normal_no_reconozco],
                       "   dijo {}".format(dichos)))
    config.VOZ_CLONADA = False

    for nombre, ok, detalle in resultados:
        print("  {}  {}{}".format("PASA " if ok else "FALLA", nombre, "\n" + detalle if detalle and not ok else ""))
    n = sum(ok for _, ok, _ in resultados)
    print("\n{} de {} casos pasan".format(n, len(resultados)))
    return n == len(resultados)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
