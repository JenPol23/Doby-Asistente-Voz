"""
generar_sinteticas.py  -  CORRE EN EL PC
Genera datos/sinteticas.csv (origen=sintetica) combinando plantillas:
  apertura + contexto + verbo + aparato + cierre
Los contextos van emparejados con el aparato que tiene sentido
(calor -> ventilador, oscuro -> bombillo, voy a soldar -> cautin, me voy a alisar el pelo -> plancha).
El cautin y la plancha solo aparecen con el aparato nombrado: nunca se encienden por contexto solo.

Reglas: "hola" nunca en ordenes, "gracias" solo en agradecer,
"dormir" solo en descansar. Sin duplicados despues de normalizar y
como maximo 80 frases por intencion, repartidas entre familias de plantillas.
Reproducible con semilla 42.

Ejecutar desde la carpeta del proyecto con:  py entrenamiento/generar_sinteticas.py
"""

import csv
import os
import random
import sys
from itertools import combinations

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "pc"))
from texto import normalizar

SEMILLA = 42
MAXIMO = 80
IGUALADOR = random.Random(SEMILLA)      # igualar(): misma cantidad de candidatas por aparato
SALIDA = os.path.join(RAIZ, "datos", "sinteticas.csv")

APERTURAS = ["", "mira", "oye", "por favor"]
CIERRES = ["", "por favor", "porfa"]

# Aparato -> sinonimos con articulo, genero y numero (para concordar adjetivos)
APARATOS = {
    "bombillo": [("el bombillo", "m", "s"), ("la bombilla", "f", "s"), ("la luz", "f", "s"),
                 ("las luces", "f", "p"), ("el foco", "m", "s")],
    "ventilador": [("el ventilador", "m", "s"), ("el abanico", "m", "s")],
    "cautin": [("el cautín", "m", "s"), ("el soldador", "m", "s")],
    "plancha": [("la plancha", "f", "s"), ("la plancha del pelo", "f", "s"), ("la planchita", "f", "s"),
                ("la alisadora", "f", "s")],
}

# ---------------- Piezas de las ordenes ----------------
CONTEXTOS_ENCENDER = {
    "ventilador": ["tengo calor", "tengo mucho calor", "hace mucho calor", "qué calor",
                   "me estoy asando", "está haciendo calor", "estoy sudando"],
    "bombillo": ["está muy oscuro", "está oscuro", "no veo nada", "ya se hizo de noche",
                 "necesito luz para leer"],
    "cautin": ["voy a soldar", "tengo que soldar unos cables", "necesito soldar"],
    "plancha": ["me voy a alisar el pelo", "me voy a arreglar el pelo", "tengo que alistarme"],
}
IMPLICITOS_ENCENDER = ["ventilador", "bombillo"]      # el contexto solo ya es una orden (nunca cautin ni plancha)
VERBOS_ENCENDER = ["prende", "enciende", "préndeme", "enciéndeme", "activa"]
VERBOS_ENCENDER_EXTRA = {}
PEDIDOS_ENCENDER = ["puedes prender", "me prendes", "podrías encender", "quiero que prendas"]
PRONOMBRES_ENCENDER = ["préndelo", "préndela", "préndelas", "enciéndelo", "enciéndela",
                       "ve prendiéndolo", "actívalo", "ya préndelo"]

CONTEXTOS_APAGAR = {
    "ventilador": ["ya no tengo calor", "tengo frío", "hace frío", "ya está fresco",
                   "me estoy congelando", "ya se refrescó"],
    "bombillo": ["ya hay suficiente luz", "ya amaneció", "la luz me molesta",
                 "ya no necesito luz", "ya entra luz por la ventana"],
    "cautin": ["ya terminé de soldar", "ya no voy a soldar"],
    "plancha": ["ya me alisé el pelo", "ya terminé de arreglarme"],
}
IMPLICITOS_APAGAR = ["ventilador"]
VERBOS_APAGAR = ["apaga", "apágame", "desactiva"]
VERBOS_APAGAR_EXTRA = {"ventilador": ["detén"]}   # nunca "para"
PEDIDOS_APAGAR = ["puedes apagar", "me apagas", "podrías apagar", "quiero que apagues"]
PRONOMBRES_APAGAR = ["apágalo", "apágala", "apágalas", "desactívalo", "ya apágalo", "ya apágala"]

# Frases implicitas y cortas (sin verbo ni aparato). Familia propia para que el
# tope de 80 no las deje por fuera. Ninguna es igual a una frase de la demo.
CORTAS_ENCENDER = ["qué oscuridad", "está muy oscuro", "no se ve nada", "está oscurísimo",
                   "qué oscuro está esto"]
CORTAS_APAGAR = ["qué frío", "está haciendo frío", "hace mucho frío", "me estoy congelando",
                 "ya no tengo calor", "ya se refrescó"]
CORTAS_DESCANSAR = ["chao", "adiós", "nos vemos", "hasta luego"]
APERTURAS_CORTAS = ["", "uy", "ay"]
APERTURAS_DESPEDIDA = ["", "bueno", "listo"]


def cortas(frases, aperturas):
    """'qué frío' -> ['qué frío', 'uy, qué frío', 'ay, qué frío']."""
    return [(a + ", " + f) if a else f for f in frases for a in aperturas]


def adornar(frase, con_cierre=True):
    """Combinaciones de apertura y cierre. Sin cierre para consultas y contextos solos."""
    salida = []
    for apertura in APERTURAS:
        for cierre in (CIERRES if con_cierre else [""]):
            if apertura == "por favor" and cierre in ("por favor", "porfa"):
                continue
            texto = frase
            if apertura:
                texto = apertura + ", " + texto
            if cierre:
                texto = texto + " " + cierre
            salida.append(texto)
    return salida


def concordar(raiz, genero, numero):
    """concordar('prendid', 'f', 'p') -> 'prendidas'."""
    return raiz + ("o" if genero == "m" else "a") + ("s" if numero == "p" else "")


def igualar(por_aparato):
    """
    {aparato: [frases]} -> lista con la MISMA cantidad de candidatas de cada aparato (la del que tiene
    menos, al azar). Asi un aparato con mas sinonimos (la plancha: 4) no sale mas veces que otro con
    menos (el cautin: 2). El total por intencion no cambia: elegir() sigue tomando MAXIMO.
    """
    n = min(len(frases) for frases in por_aparato.values())
    return [f for aparato in APARATOS for f in IGUALADOR.sample(por_aparato[aparato], n)]


def ordenes(contextos, implicitos, verbos, extra, pedidos, pronombres):
    """Familias de plantillas para encender o apagar."""
    familias = {"con_contexto": [], "sin_contexto": [], "solo_contexto": [],
                "sin_aparato": [], "varios": []}
    con_contexto = {a: [] for a in APARATOS}
    sin_contexto = {a: [] for a in APARATOS}
    for aparato, sinonimos in APARATOS.items():
        todos_verbos = verbos + extra.get(aparato, [])
        for sustantivo, _, _ in sinonimos:
            for verbo in todos_verbos:
                sin_contexto[aparato] += adornar("{} {}".format(verbo, sustantivo))
                for contexto in contextos[aparato]:
                    con_contexto[aparato] += adornar("{}, {} {}".format(contexto, verbo, sustantivo))
            for pedido in pedidos:
                sin_contexto[aparato] += adornar("{} {}".format(pedido, sustantivo))
        if aparato in implicitos:
            for contexto in contextos[aparato]:
                familias["solo_contexto"] += adornar(contexto, con_cierre=False)
    familias["con_contexto"] = igualar(con_contexto)
    familias["sin_contexto"] = igualar(sin_contexto)
    for pronombre in pronombres:
        familias["sin_aparato"] += adornar(pronombre)
    for a, b in combinations(APARATOS, 2):
        for verbo in verbos[:3]:
            familias["varios"] += adornar("{} {} y {}".format(verbo, APARATOS[a][0][0], APARATOS[b][0][0]))
    return familias


# ---------------- Familias por intencion ----------------
def familias_apagar_todo():
    verbos = ["apaga", "apágame", "desactiva", "desconecta"]
    objetos = ["todo", "todos los aparatos", "todos los dispositivos",
               "todo lo que esté prendido", "todo lo de la casa"]
    contextos = ["ya me voy de la casa", "salgo de viaje", "no voy a estar en la casa",
                 "ya acabamos por hoy", "me voy a acostar"]
    directas = ["{} {}".format(v, o) for v in verbos for o in objetos]
    estado = ["deja todo apagado", "quiero todo apagado", "pon todo en apagado",
              "apaga absolutamente todo", "apágalo todo"]
    return {
        "directa": [t for d in directas for t in adornar(d)],
        "con_contexto": [t for c in contextos for d in directas[:10] for t in adornar("{}, {}".format(c, d))],
        "estado": [t for e in estado for t in adornar(e)],
    }


def familias_descansar():
    directas = ["descansa", "ya puedes descansar", "puedes descansar", "vete a descansar",
                "ve a descansar", "tómate un descanso", "a dormir", "vete a dormir",
                "ya puedes irte a dormir", "duérmete", "puedes retirarte"]
    cierres = ["eso es todo", "eso era todo", "no necesito nada más", "ya no te necesito",
               "por ahora es todo", "ya terminamos"]
    contextos = ["listo", "bueno", "ya terminamos", "eso era todo"]
    return {
        "corta": cortas(CORTAS_DESCANSAR, APERTURAS_DESPEDIDA),
        "directa": [t for d in directas for t in adornar(d)],
        "fin_conversacion": [t for c in cierres for t in adornar(c)],
        "con_contexto": [t for c in contextos for d in directas
                         for t in adornar("{}, {}".format(c, d)) if c != d],
    }


def familias_consultar_estado():
    por_aparato = {a: [] for a in APARATOS}
    for aparato, sinonimos in APARATOS.items():
        for sustantivo, genero, numero in sinonimos:
            esta = "está" if numero == "s" else "están"
            sigue = "sigue" if numero == "s" else "siguen"
            frases = por_aparato[aparato]
            for raiz in ("prendid", "encendid", "apagad"):
                adj = concordar(raiz, genero, numero)
                frases += adornar("{} {} {}".format(sustantivo, esta, adj), False)
                frases += adornar("{} {} {}".format(esta, adj, sustantivo), False)
                frases += adornar("{} {} {}".format(sustantivo, sigue, adj), False)
                frases += adornar("dime si {} {} {}".format(sustantivo, esta, adj), False)
            frases += adornar("cómo {} {}".format(esta, sustantivo), False)
    por_aparato = igualar(por_aparato)
    generales = ["qué está prendido", "qué está encendido", "qué está apagado",
                 "qué aparatos están prendidos", "qué quedó prendido", "hay algo prendido",
                 "hay algo encendido", "cómo están los aparatos", "revisa qué está encendido",
                 "me dices qué está prendido", "cuáles están encendidos", "todo está apagado",
                 "en qué estado están los aparatos"]
    return {"por_aparato": por_aparato,
            "general": [t for g in generales for t in adornar(g, False)]}


def familias_agradecer():
    base = ["gracias", "muchas gracias", "mil gracias", "te lo agradezco", "muy amable",
            "qué amable", "gracias por la ayuda", "gracias por todo", "te agradezco mucho"]
    prefijos = ["listo", "perfecto", "excelente", "muy bien", "qué bien", "súper"]
    elogios = ["excelente trabajo", "muy bien hecho", "eres el mejor", "qué buen trabajo",
               "así me gusta"]
    return {"base": base,
            "con_prefijo": ["{}, {}".format(p, b) for p in prefijos for b in base],
            "elogio": elogios + ["{}, {}".format(e, b) for e in elogios for b in base[:3]]}


def familias_saludo():
    base = ["hola", "buenos días", "buenas tardes", "buenas noches", "buenas", "qué más", "qué tal"]
    preguntas = ["cómo estás", "cómo vas", "cómo te va", "cómo amaneciste", "qué hay de nuevo",
                 "cómo te ha ido", "estás ahí", "me escuchas"]
    return {"base": base + ["oye, " + b for b in base],
            "con_pregunta": ["{}, {}".format(b, p) for b in base for p in preguntas],
            "pregunta": preguntas + ["oye, " + p for p in preguntas]}


def familias_fuera_de_dominio():
    # Solo sustantivos en singular (sin "la luz", que no se compra ni tiene color)
    cosas = [(a, s, g) for a, sinonimos in APARATOS.items() for s, g, n in sinonimos
             if n == "s" and s != "la luz"]
    por_aparato = {a: [] for a in APARATOS}
    for aparato, sustantivo, genero in cosas:
        nombre = sustantivo.split(" ", 1)[1]
        un = "un" if genero == "m" else "una"
        otro = "otro" if genero == "m" else "otra"
        frases = por_aparato[aparato]
        for color in ("blanc", "negr", "roj"):
            frases.append("{} es {}".format(sustantivo, concordar(color, genero, "s")))
        frases.append("mañana compro {} {}".format(otro, nombre))
        frases.append("cuánto cuesta {} {}".format(un, nombre))
        frases.append("me regalaron {} {}".format(un, nombre))
        frases.append("dónde compro {} {}".format(un, nombre))
        for familiar in ("mi mamá", "mi abuela", "mi hermano"):
            frases.append("{} de {} es muy {}".format(sustantivo, familiar,
                                                      concordar("viej", genero, "s")))
    aparatos = igualar(por_aparato)
    generales = ["qué hora es", "cómo va a estar el clima", "cuéntame un chiste", "pon música",
                 "qué día es hoy", "cuánto es dos más dos", "llama a mi mamá",
                 "pide un domicilio", "tengo hambre", "estoy aburrido", "quién ganó el partido",
                 "recuérdame comprar leche", "cuál es la capital de Colombia",
                 "qué noticias hay", "busca una receta de arepas", "cuántos años tienes",
                 "qué película me recomiendas", "cómo se dice perro en inglés"]
    return {"aparatos_no_orden": aparatos,
            "general": [t for g in generales for t in adornar(g)]}


# ---------------- Seleccion ----------------
def elegir(familias, azar, vistos):
    """Quita duplicados (normalizados) y toma hasta MAXIMO repartiendo entre familias."""
    limpias = {}
    for nombre, frases in familias.items():
        lista = []
        for frase in frases:
            clave = normalizar(frase)
            if clave not in vistos:
                vistos.add(clave)
                lista.append(frase)
        azar.shuffle(lista)
        limpias[nombre] = lista
    unicas = sum(len(l) for l in limpias.values())
    elegidas = []
    while len(elegidas) < MAXIMO and any(limpias.values()):
        for nombre in limpias:
            if limpias[nombre] and len(elegidas) < MAXIMO:
                elegidas.append(limpias[nombre].pop())
    return elegidas, unicas


def revisar_reglas(filas):
    """'hola' nunca en ordenes, 'gracias' solo en agradecer, 'dormir' solo en descansar."""
    reglas = {"hola": {"saludo"}, "gracias": {"agradecer"}, "dormir": {"descansar"}}
    errores = 0
    for texto, intencion in filas:
        palabras = normalizar(texto).split()
        for palabra, permitidas in reglas.items():
            if palabra in palabras and intencion not in permitidas:
                errores += 1
                print("  REGLA ROTA: '{}' en {} -> {}".format(palabra, intencion, texto))
    return errores


# ---------------- Programa principal ----------------
azar = random.Random(SEMILLA)
vistos = set()
generadores = {
    "saludo": familias_saludo(),
    # La familia "corta" va primero: gana ante duplicados y entra primero al reparto
    "encender": {"corta": cortas(CORTAS_ENCENDER, APERTURAS_CORTAS),
                 **ordenes(CONTEXTOS_ENCENDER, IMPLICITOS_ENCENDER, VERBOS_ENCENDER,
                           VERBOS_ENCENDER_EXTRA, PEDIDOS_ENCENDER, PRONOMBRES_ENCENDER)},
    "apagar": {"corta": cortas(CORTAS_APAGAR, APERTURAS_CORTAS),
               **ordenes(CONTEXTOS_APAGAR, IMPLICITOS_APAGAR, VERBOS_APAGAR,
                         VERBOS_APAGAR_EXTRA, PEDIDOS_APAGAR, PRONOMBRES_APAGAR)},
    "apagar_todo": familias_apagar_todo(),
    "descansar": familias_descansar(),
    "consultar_estado": familias_consultar_estado(),
    "agradecer": familias_agradecer(),
    "fuera_de_dominio": familias_fuera_de_dominio(),
}

filas = []
print("Frases sinteticas por intencion (unicas tras normalizar -> elegidas):")
for intencion, familias in generadores.items():
    elegidas, unicas = elegir(familias, azar, vistos)
    print("  {:18} {:6d} -> {:3d}".format(intencion, unicas, len(elegidas)))
    filas += [(texto, intencion) for texto in elegidas]

errores = revisar_reglas(filas)
print("Reglas de palabras: {}".format("OK" if errores == 0 else "{} errores".format(errores)))

with open(SALIDA, "w", encoding="utf-8", newline="") as f:
    escritor = csv.writer(f)
    escritor.writerow(["texto", "intencion", "origen"])
    for texto, intencion in filas:
        escritor.writerow([texto, intencion, "sintetica"])
print("Guardadas {} frases en {}".format(len(filas), os.path.abspath(SALIDA)))

print("\n5 ejemplos por intencion:")
for intencion in generadores:
    grupo = [t for t, i in filas if i == intencion]
    print("  {}:".format(intencion))
    for texto in azar.sample(grupo, min(5, len(grupo))):
        print("     -", texto)
