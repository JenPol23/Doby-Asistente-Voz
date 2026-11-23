"""
prueba_firmware.py  -  CORRE EN EL PC, SIN ESP32
Corre el firmware esp32/main.py (MicroPython) en el Python del PC, con machine (Pin, I2S), network (WLAN),
secretos, socket (API de MicroPython sobre un socket local) y time.ticks_ms/ticks_diff/sleep_ms simulados,
y prueba los reles y la seguridad del cautin y la plancha (CALIENTES):
  RELE 1/2/4 y RELE 5 -> ERR; PC vivo (PING continuo) -> nada se apaga; reconexion rapida -> nada se apaga;
  PC cerrado -> se apagan pasada la gracia (el ventilador no); PC conectado pero mudo -> se apagan;
  WiFi perdido -> se apagan al instante; TODOS 0 incluye el rele 4.
Los tiempos se acortan SOLO dentro de la prueba (SEG_GRACIA 15 -> 3 s, SEG_SIN_ORDENES 60 -> 4 s); el
servidor escucha en 127.0.0.1 y en un puerto libre. El archivo esp32/main.py no se modifica.

Uso:  py pruebas/prueba_firmware.py [ruta de main.py]     (codigo de salida 1 si algun caso falla)
"""
import errno
import os
import socket as _socket
import sys
import threading
import time
import types

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "esp32", "main.py")
GRACIA, SIN_ORDENES = 3, 4                     # acortados SOLO para la prueba (en la placa: 15 y 60)

# ---------------- MicroPython simulado ----------------
time.ticks_ms = lambda: int(time.monotonic() * 1000)
time.ticks_diff = lambda a, b: a - b
time.sleep_ms = lambda ms: time.sleep(ms / 1000)


class Pin:
    OUT = 1
    todos = {}

    def __init__(self, gpio, modo=None, value=None):
        self.gpio, self.v = gpio, value
        Pin.todos[gpio] = self

    def value(self, v=None):
        if v is None:
            return self.v
        self.v = v


class I2S:
    RX = TX = MONO = 0

    def __init__(self, *a, **k):
        pass

    def readinto(self, mv):
        return len(mv)

    def write(self, mv):
        return len(mv)


class WLAN:
    conectado = True
    PM_NONE = 0

    def __init__(self, *a):
        pass

    def active(self, *a):
        pass

    def config(self, *a, **k):
        return 10

    def isconnected(self):
        return WLAN.conectado

    def connect(self, *a):
        WLAN.conectado = True

    def disconnect(self):
        pass

    def ifconfig(self):
        return ("127.0.0.1",)


class SocketMP:
    """Socket con la API de MicroPython que usa main.py (readline/readinto/write con timeout -> OSError)."""

    def __init__(self, s=None):
        self.s = s or _socket.socket()
        self.buf = b""

    def setsockopt(self, *a):
        self.s.setsockopt(*a)

    def bind(self, d):
        self.s.bind(d)

    def listen(self, n):
        self.s.listen(n)

    def setblocking(self, b):
        self.s.setblocking(b)

    def settimeout(self, t):
        self.s.settimeout(t)

    def accept(self):
        c, d = self.s.accept()
        c.setblocking(True)
        return SocketMP(c), d

    def _recv(self):
        try:
            return self.s.recv(4096)
        except _socket.timeout:
            raise OSError(errno.ETIMEDOUT, "timeout")

    def readline(self):
        while b"\n" not in self.buf:
            datos = self._recv()
            if not datos:
                linea, self.buf = self.buf, b""
                return linea
            self.buf += datos
        linea, self.buf = self.buf.split(b"\n", 1)
        return linea + b"\n"

    def readinto(self, mv):
        if not self.buf:
            self.buf = self._recv()
        n = min(len(mv), len(self.buf))
        mv[:n] = self.buf[:n]
        self.buf = self.buf[n:]
        return n

    def write(self, b):
        self.s.sendall(bytes(b))

    def close(self):
        self.s.close()


sys.modules["machine"] = types.SimpleNamespace(Pin=Pin, I2S=I2S)
sys.modules["network"] = types.SimpleNamespace(WLAN=WLAN, STA_IF=0)
sys.modules["secretos"] = types.SimpleNamespace(RED="red", CLAVE="clave")
sys.modules["socket"] = types.SimpleNamespace(socket=SocketMP, SOL_SOCKET=_socket.SOL_SOCKET,
                                              SO_REUSEADDR=_socket.SO_REUSEADDR)

libre = _socket.socket()
libre.bind(("127.0.0.1", 0))
PUERTO = libre.getsockname()[1]
libre.close()
codigo = open(RUTA, encoding="utf-8").read()
for viejo, nuevo in (('"0.0.0.0"', '"127.0.0.1"'), ("PUERTO = 5000", "PUERTO = {}".format(PUERTO)),
                     ("SEG_GRACIA = 15", "SEG_GRACIA = {}".format(GRACIA)),
                     ("SEG_SIN_ORDENES = 60", "SEG_SIN_ORDENES = {}".format(SIN_ORDENES))):
    assert viejo in codigo, viejo
    codigo = codigo.replace(viejo, nuevo)
threading.Thread(target=lambda: exec(compile(codigo, "main.py", "exec"), {"__name__": "__main__"}), daemon=True).start()
time.sleep(1.5)

# ---------------- Pruebas ----------------
GPIO = {1: 10, 2: 11, 3: 12, 4: 13}
resultados = []


def estado():
    """{rele: 'ON'/'off'} (activo en bajo: 0 = encendido)."""
    return {k: "ON" if Pin.todos[g].value() == 0 else "off" for k, g in GPIO.items()}


def informe(nombre, ok, detalle=""):
    resultados.append(ok)
    print("[{}] {}  {}".format("PASA" if ok else "FALLA", nombre, detalle))


class Pc:
    def __init__(self):
        self.s = _socket.create_connection(("127.0.0.1", PUERTO), timeout=5)
        self.f = self.s.makefile("rb")

    def orden(self, texto):
        self.s.sendall((texto + "\n").encode())
        return self.f.readline().decode().strip()

    def cerrar(self):
        self.f.close()
        self.s.close()


def esperar(seg, pc=None):
    """Espera 'seg' s; con pc, manda PING cada 0.5 s (como el MIC continuo de Doby)."""
    fin = time.monotonic() + seg
    while time.monotonic() < fin:
        if pc:
            pc.orden("PING")
        time.sleep(0.5)


pc = Pc()
r = [pc.orden("RELE 1 1"), pc.orden("RELE 2 1"), pc.orden("RELE 4 1"), pc.orden("RELE 5 1")]
informe("RELE 1/2/4 -> OK, RELE 5 -> ERR; reles 1, 2 y 4 encendidos", r == ["OK", "OK", "OK", "ERR"]
        and estado() == {1: "ON", 2: "ON", 3: "off", 4: "ON"}, "{} {}".format(r, estado()))
esperar(SIN_ORDENES + GRACIA + 1, pc)
informe("PC vivo (PING continuo) {} s: no se apaga nada".format(SIN_ORDENES + GRACIA + 1),
        estado() == {1: "ON", 2: "ON", 3: "off", 4: "ON"}, str(estado()))

pc.cerrar()
time.sleep(1.0)
pc = Pc()                                      # reconexion rapida (como Doby tras un atasco del WiFi)
esperar(GRACIA + 2, pc)
informe("Reconexion al 1 s: el cautin y la plancha siguen encendidos", estado()[2] == "ON" and estado()[4] == "ON", str(estado()))

pc.cerrar()
time.sleep(GRACIA - 1)
informe("PC cerrado, antes de la gracia: siguen encendidos", estado()[2] == "ON" and estado()[4] == "ON", str(estado()))
time.sleep(2.5)
informe("PC cerrado, pasada la gracia: cautin y plancha APAGADOS, ventilador sigue",
        estado() == {1: "ON", 2: "off", 3: "off", 4: "off"}, str(estado()))

pc = Pc()
pc.orden("RELE 2 1")
pc.orden("RELE 4 1")
time.sleep(SIN_ORDENES + GRACIA + 2.5)          # PC "colgado": conectado pero sin mandar nada
informe("PC conectado pero mudo {} s + gracia: cautin y plancha APAGADOS".format(SIN_ORDENES),
        estado() == {1: "ON", 2: "off", 3: "off", 4: "off"}, str(estado()))
pc.cerrar()

pc = Pc()
pc.orden("RELE 4 1")
WLAN.conectado = False                         # se cae el WiFi (revisar_wifi mira cada 5 s)
fin = time.monotonic() + 7
while time.monotonic() < fin and estado()[4] == "ON":
    time.sleep(0.2)
informe("WiFi perdido: plancha apagada sin esperar la gracia", estado()[4] == "off", str(estado()))
pc.cerrar()
time.sleep(2)

pc = Pc()
r = [pc.orden("RELE 3 1"), pc.orden("RELE 4 1"), pc.orden("TODOS 0")]
informe("TODOS 0 apaga tambien el rele 4 (plancha)", r == ["OK", "OK", "OK"]
        and estado() == {1: "off", 2: "off", 3: "off", 4: "off"}, "{} {}".format(r, estado()))
pc.cerrar()
print("\n{} de {} casos pasan".format(sum(resultados), len(resultados)))
sys.exit(0 if all(resultados) else 1)
