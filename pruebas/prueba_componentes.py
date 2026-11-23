# ============================================================
#  PRUEBA DE COMPONENTES  -  ESP32-S3 (N16R8)
#  INMP441  +  MAX98357  +  Rele de 4 canales
#  MicroPython / Thonny
# ------------------------------------------------------------
#  IMPORTANTE: haz todas las conexiones del rele con el 110V
#  DESENCHUFADO. Solo conecta a la toma para correr la prueba.
# ============================================================

from machine import Pin, I2S
import math
import struct
import time

# ---------------- PINES ----------------
# Microfono INMP441
MIC_SCK = 4
MIC_WS = 5
MIC_SD = 6

# Amplificador MAX98357
AMP_BCLK = 15
AMP_LRC = 16
AMP_DIN = 7

# Rele de 4 canales (la mayoria son ACTIVOS EN BAJO: 0 = encendido)
PINES_RELE = [10, 11, 12, 13]   # mismos que PINES_RELE de esp32/main.py (reles 1 a 4)
NOMBRES_RELE = ["GPIO10 - rele 1 - ventilador", "GPIO11 - rele 2 - cautin",
                "GPIO12 - rele 3 - bombillo", "GPIO13 - rele 4 - plancha"]
RELE_ACTIVO_EN_BAJO = True

# Tiempo (segundos) que queda encendido cada canal
TIEMPOS_RELE = [8, 1, 5, 1]   # ventilador 8 s, bombillo 5 s; cautin y plancha 1 s (se calientan)

# ---------------- AUDIO ----------------
TASA = 16000        # muestras por segundo
VOLUMEN = 0.25      # 0.0 a 1.0  -> bajo, protege el parlante de 1.5 W


# ============================================================
#  PRUEBA 1: RELES
# ============================================================
def prueba_reles():
    print()
    print("--- PRUEBA 1: RELES ---")
    print("Debes escuchar un 'clic' y ver el LED de cada canal.")
    print()

    apagado = 1 if RELE_ACTIVO_EN_BAJO else 0
    encendido = 0 if RELE_ACTIVO_EN_BAJO else 1

    reles = [Pin(p, Pin.OUT, value=apagado) for p in PINES_RELE]
    time.sleep(1)

    for i, rele in enumerate(reles):
        print("  Encendiendo:", NOMBRES_RELE[i], "por", TIEMPOS_RELE[i], "s")
        rele.value(encendido)
        time.sleep(TIEMPOS_RELE[i])
        rele.value(apagado)
        print("  Apagado")
        time.sleep(1)

    print()
    print("Si NO hubo clics, prueba cambiando RELE_ACTIVO_EN_BAJO a False.")


# ============================================================
#  PRUEBA 2: PARLANTE (MAX98357)
# ============================================================
def generar_tono(audio, frecuencia, segundos):
    muestras_ciclo = TASA // frecuencia
    ciclo = bytearray()
    for i in range(muestras_ciclo):
        valor = int(32767 * VOLUMEN * math.sin(2 * math.pi * i / muestras_ciclo))
        ciclo += struct.pack("<h", valor)

    repeticiones = int(segundos * TASA / muestras_ciclo)
    for _ in range(repeticiones):
        audio.write(ciclo)


def prueba_parlante():
    print()
    print("--- PRUEBA 2: PARLANTE ---")
    print("Debes escuchar tres pitos seguidos, cada vez mas agudos.")
    print()

    audio = I2S(
        0,
        sck=Pin(AMP_BCLK),
        ws=Pin(AMP_LRC),
        sd=Pin(AMP_DIN),
        mode=I2S.TX,
        bits=16,
        format=I2S.MONO,
        rate=TASA,
        ibuf=4000,
    )

    try:
        for frecuencia in (440, 660, 880):
            print("  Tono de", frecuencia, "Hz")
            generar_tono(audio, frecuencia, 0.5)
            time.sleep(0.2)
    finally:
        audio.deinit()

    print()
    print("Si no suena nada, revisa la bornera del parlante y el VIN de 5V.")
    print("Si suena muy bajo, sube VOLUMEN poco a poco (maximo 0.5).")


# ============================================================
#  PRUEBA 3: MICROFONO (INMP441)
# ============================================================
def calcular_nivel(buf, leidos):
    total = 0
    cuenta = 0
    # Cada muestra son 4 bytes. Revisamos 1 de cada 8 para ir rapido.
    for i in range(0, leidos - 3, 32):
        valor = struct.unpack_from("<i", buf, i)[0]
        total += abs(valor >> 16)
        cuenta += 1
    if cuenta == 0:
        return 0
    return total // cuenta


def prueba_microfono(segundos=12):
    print()
    print("--- PRUEBA 3: MICROFONO ---")
    print("Habla, aplaude o silba cerca del microfono.")
    print("Las barras deben crecer con el ruido y bajar en silencio.")
    print()

    mic = I2S(
        1,
        sck=Pin(MIC_SCK),
        ws=Pin(MIC_WS),
        sd=Pin(MIC_SD),
        mode=I2S.RX,
        bits=32,
        format=I2S.MONO,
        rate=TASA,
        ibuf=4000,
    )

    buf = bytearray(2048)
    fin = time.ticks_add(time.ticks_ms(), int(segundos * 1000))

    try:
        while time.ticks_diff(fin, time.ticks_ms()) > 0:
            leidos = mic.readinto(buf)
            if leidos:
                nivel = calcular_nivel(buf, leidos)
                barras = "#" * min(nivel // 40, 40)
                print("{:6d} |{}".format(nivel, barras))
    finally:
        mic.deinit()

    print()
    print("Si el numero se queda en 0, revisa VDD (3V3), GND, L/R y las soldaduras.")
    print("Si el numero queda altisimo y fijo, revisa que SD no este suelto.")


# ============================================================
#  PROGRAMA PRINCIPAL
# ============================================================
def main():
    print("============================================")
    print(" PRUEBA DE MONTAJE - ESP32-S3")
    print("============================================")

    prueba_reles()
    time.sleep(1)

    prueba_parlante()
    time.sleep(1)

    prueba_microfono(12)

    print()
    print("============================================")
    print(" PRUEBAS TERMINADAS")
    print("============================================")


main()