"""
esp32_cliente.py  -  CORRE EN EL PC
Cliente TCP del protocolo de Doby (la ESP32 es el servidor, puerto 5000).

  PING                -> PONG
  MIC                 -> 4096 bytes (1024 muestras int32 LE)
  HABLAR <n> + n bytes PCM int16 LE -> OK al terminar de sonar
  RELE <k> <1|0>      -> OK o ERR
  TODOS 0             -> OK

Todas las lecturas pasan por un unico makefile('rb') (readline y read),
para no perder bytes mezclando metodos de lectura.
"""

import socket
import time

import numpy as np

import config

BYTES_MIC = 4096                # 1024 muestras int32 = 64 ms de audio
TIMEOUT = 5.0                   # segundos para las ordenes cortas
TIMEOUT_MIC = 6.0               # un bloque tarda 64 ms, pero un atasco del WiFi puede pasar de 2 s: esperar pierde menos audio que reconectar
ESPERA_REINTENTO = 2.0          # segundos entre intentos de conexion


class Esp32Cliente:
    def __init__(self, ip=config.IP_ESP32, puerto=config.PUERTO):
        self.ip = ip
        self.puerto = puerto
        self.sock = None
        self.lector = None

    # ---------------- Conexion ----------------
    def conectar(self, intentos=None):
        """
        Intenta conectar cada 2 s hasta lograrlo (intentos=None, como siempre) o hasta 'intentos'
        veces (al cerrar Doby, para no quedarse esperando). True si conecto. No cambia los reles.
        """
        self.cerrar()
        intento = 0
        while True:
            intento += 1
            try:
                sock = socket.create_connection((self.ip, self.puerto), timeout=TIMEOUT)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock = sock
                self.lector = sock.makefile("rb")
                print("Conectado a la ESP32 en {}:{}".format(self.ip, self.puerto))
                return True
            except OSError as e:
                if intentos is not None and intento >= intentos:
                    print("No se pudo conectar a la ESP32 (intento {}): {}.".format(intento, e))
                    return False
                print("No se pudo conectar a la ESP32 (intento {}): {}. Reintento en 2 s...".format(intento, e))
                time.sleep(ESPERA_REINTENTO)

    def cerrar(self):
        for objeto in (self.lector, self.sock):
            if objeto is not None:
                try:
                    objeto.close()
                except OSError:
                    pass
        self.sock = None
        self.lector = None

    # ---------------- Lectura (solo por self.lector) ----------------
    def _leer_linea(self):
        linea = self.lector.readline()
        if not linea.endswith(b"\n"):
            raise ConnectionError("la ESP32 cerro la conexion")
        return linea.decode("ascii").strip()

    def _leer_exacto(self, cantidad):
        datos = self.lector.read(cantidad)
        if datos is None or len(datos) < cantidad:
            raise ConnectionError("la ESP32 cerro la conexion")
        return datos

    # ---------------- Envio con reintento ----------------
    def _con_reintento(self, funcion):
        """Ejecuta la orden; si se cae la conexion, reconecta y la repite UNA vez."""
        if self.sock is None:
            self.conectar()
        try:
            return funcion()
        except (OSError, ConnectionError, UnicodeDecodeError) as e:
            print("Se perdio la conexion ({}). Reconectando para repetir la orden...".format(e))
            self.conectar()
            return funcion()

    def _orden_linea(self, texto):
        """Envia una orden de una linea y devuelve la respuesta de una linea."""
        self.sock.settimeout(TIMEOUT)
        self.sock.sendall((texto + "\n").encode("ascii"))
        return self._leer_linea()

    # ---------------- Ordenes del protocolo ----------------
    def ping(self):
        """True si la ESP32 responde PONG."""
        return self._con_reintento(lambda: self._orden_linea("PING")) == "PONG"

    def leer_mic(self):
        """Devuelve 1024 muestras crudas int32 del microfono (sin convertir)."""
        def orden():
            self.sock.settimeout(TIMEOUT_MIC)
            self.sock.sendall(b"MIC\n")
            return self._leer_exacto(BYTES_MIC)
        return np.frombuffer(self._con_reintento(orden), dtype="<i4")

    # Para tener varios MIC en vuelo (entrada_audio.py): se separa el envio de
    # la lectura. Sin reintento: quien los usa lleva la cuenta de los pendientes
    # y reconecta si se cae la conexion.
    def pedir_mic(self):
        """Envia MIC sin esperar la respuesta."""
        self.sock.settimeout(TIMEOUT_MIC)
        self.sock.sendall(b"MIC\n")

    def recibir_mic(self):
        """Lee la respuesta de un MIC pedido antes: 1024 muestras crudas int32."""
        self.sock.settimeout(TIMEOUT_MIC)
        return np.frombuffer(self._leer_exacto(BYTES_MIC), dtype="<i4")

    def rele(self, k, estado):
        """Enciende (estado=1/True) o apaga (0/False) el rele k (1..4). True si OK."""
        texto = "RELE {} {}".format(int(k), 1 if estado else 0)
        return self._con_reintento(lambda: self._orden_linea(texto)) == "OK"

    def todos_apagados(self):
        """Apaga los 4 reles. True si OK."""
        return self._con_reintento(lambda: self._orden_linea("TODOS 0")) == "OK"

    def hablar(self, pcm):
        """
        Reproduce PCM int16 mono 16 kHz en el parlante de la ESP32.
        Devuelve True si la ESP32 respondio OK. Si falla la conexion, reconecta
        y devuelve False SIN repetir el audio (Doby no habla dos veces).
        """
        if isinstance(pcm, np.ndarray):
            datos = pcm.astype("<i2").tobytes()
        else:
            datos = bytes(pcm)
        if len(datos) % 2:
            datos = datos[:-1]                     # siempre muestras completas

        if self.sock is None:
            self.conectar()
        duracion = len(datos) / 2 / config.TASA
        try:
            self.sock.settimeout(duracion + TIMEOUT)
            self.sock.sendall("HABLAR {}\n".format(len(datos)).encode("ascii") + datos)
            return self._leer_linea() == "OK"
        except (OSError, ConnectionError, UnicodeDecodeError) as e:
            print("Se perdio la conexion durante HABLAR ({}). Reconecto sin repetir el audio.".format(e))
            self.conectar()
            return False
