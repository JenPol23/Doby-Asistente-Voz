# Conexiones y protocolo de Doby

## Pines de la ESP32-S3 (N16R8)

Sacados de `esp32/main.py` y `pruebas/prueba_componentes.py`.

| Componente | Señal | GPIO |
|---|---|---|
| Micrófono INMP441 (I2S 1, RX, 32 bits, mono, 16 kHz) | SCK | 4 |
| | WS | 5 |
| | SD | 6 |
| Amplificador MAX98357 (I2S 0, TX, 16 bits, mono, 16 kHz) | BCLK | 15 |
| | LRC | 16 |
| | DIN | 7 |
| Relé 1: ventilador | IN1 | 10 |
| Relé 2: cautín | IN2 | 11 |
| Relé 3: bombillo | IN3 | 12 |
| Relé 4: plancha de cabello | IN4 | 13 |

- El módulo de relés es **activo en bajo**: `0` = encendido, `1` = apagado. Al arrancar, el firmware deja los 4 apagados antes de conectarse al WiFi.
- El mapa aparato → relé del PC está en `pc/config.py` (`APARATOS`) y debe coincidir con `PINES_RELE` de `esp32/main.py`.
- INMP441: VDD a **3V3** y GND (según el mensaje de diagnóstico de `pruebas/prueba_componentes.py`).
- **POR VERIFICAR (no está en el código):** a qué se conecta el pin L/R del INMP441, la alimentación y los pines GAIN/SD del MAX98357, y cómo se alimenta el módulo de relés (5 V y JD-VCC). Hay que comprobarlo en el montaje real y anotarlo aquí.

> ⚠️ Los aparatos van a **110 V**. Lee la sección [Seguridad eléctrica (110 V)](#seguridad-eléctrica-110-v) antes de conectar nada.

## Seguridad eléctrica (110 V)

El lado de potencia del módulo de relés maneja la tensión de la toma de corriente, que **puede matar**. Las pruebas son de bajo voltaje hasta el paso «bombillo» de [GUIA_PARA_OTROS.md](GUIA_PARA_OTROS.md).

**Antes de conectar**
- **Todo el cableado de 110 V se hace con el enchufe desconectado de la toma.** No basta con apagar Doby o la ESP32.
- Cada relé corta **una sola fase** del aparato, en serie: toma → COM del relé → NO del relé → aparato. El otro conductor va directo de la toma al aparato.
  - Usa NO (normalmente abierto) para que, sin señal, el aparato quede apagado.
  - **POR VERIFICAR** en el montaje real qué borne (NO o NC) se usó. Se comprueba con el multímetro en continuidad, sin 110 V: con el relé en reposo, COM–NO debe estar abierto.
- Revisa que la **corriente nominal de cada relé** (impresa en el relé, por ejemplo «10A 250VAC») supere la del aparato.
  - La plancha de cabello y el cautín consumen bastante: mira la potencia en su etiqueta y divide entre 110 V.
  - **POR VERIFICAR** la potencia de los aparatos usados y el modelo del módulo de relés.
- Cable de calibre adecuado, sin cobre a la vista. Bornes bien apretados y cubiertos. Nada de empalmes con cinta sobre la mesa.
- El lado de 110 V queda **separado** de la ESP32, la protoboard y los cables de señal, y sobre una superficie que no conduzca.
- Una regleta con interruptor o un breaker al alcance de la mano permite cortar todo de una vez.

**Al probar**
- Prueba primero los relés **sin carga** (solo se oye el clic y se ve el LED). Después, con el **bombillo**. Al final, con el cautín y la plancha. El orden detallado está en [GUIA_PARA_OTROS.md](GUIA_PARA_OTROS.md).
- **Nunca alimentes la ESP32 por USB y por la fuente al mismo tiempo.**
- El cautín y la plancha se calientan: ponlos en su soporte y lejos de cables, papel y plástico.
  - Aunque Doby los apaga solo (ver abajo), **no los dejes sin vigilancia**.
- Si un relé queda pegado (el aparato no se apaga con `RELE k 0`), **desconecta el enchufe** antes de tocar nada.

> El apagado automático por software (ver la sección siguiente) es una ayuda, **no reemplaza** un corte físico ni la supervisión de una persona.

## Red

- La ESP32 se conecta como estación a una red WiFi de **2.4 GHz**, con nombre y clave en `esp32/secretos.py` (plantilla: `esp32/secretos.ejemplo.py`). Para el micrófono, la potencia de transmisión se baja a 10 dBm.
- La ESP32 es el **servidor TCP** en el puerto **5000** y atiende a un solo PC a la vez.
- El PC se conecta a la IP de `IP_ESP32` en `pc/config.py`. Esa IP es la que imprime la placa al arrancar (`Doby listo en <IP>:5000`) y puede cambiar si se reconecta el punto de acceso: en ese caso se actualiza en `pc/config.py`.

## Protocolo PC ↔ ESP32

Una orden por línea, en ASCII, terminada en `\n`.

| Orden del PC | Respuesta de la ESP32 |
|---|---|
| `PING` | `PONG` |
| `MIC` | 4096 bytes: 1024 muestras int32 little-endian del INMP441 (64 ms a 16 kHz) |
| `HABLAR <n>` seguido de `n` bytes de PCM int16 LE, mono, 16 kHz | la ESP32 recibe la frase entera, la reproduce y responde `OK` al terminar de sonar |
| `RELE <k> <1\|0>` (k = 1..4) | `OK`, o `ERR` si k o el valor no son válidos |
| `TODOS 0` | apaga los 4 relés y responde `OK` |
| cualquier otra cosa | `ERR` |

- El PC mantiene siempre **2 pedidos `MIC` en vuelo** para no perder audio entre bloques. Antes de `HABLAR` o `RELE` vacía los pendientes (`pc/entrada_audio.py`).
- La muestra del micrófono se convierte en el PC con `muestra >> 16` y se le quita la media.

## Seguridad de los aparatos que se calientan (cautín y plancha)

En la ESP32 (`esp32/main.py`, `CALIENTES = (2, 4)`):
- Si el PC se desconecta y no vuelve en **15 s**, apaga los relés 2 y 4.
- Si el PC está conectado pero no manda **ninguna orden en 60 s**, lo da por perdido y aplica la regla anterior.
- Si se pierde el WiFi, apaga los relés 2 y 4 de inmediato.
- El ventilador y el bombillo conservan su estado.

En el PC (`pc/doby.py`):
- **Apagado automático:** el cautín y la plancha se apagan solos tras `APAGADO_AUTOMATICO` = 10 min encendidos, y Doby lo avisa («Por seguridad, apagué el cautín»).
- **Al cerrar Doby** (normal, Ctrl+C o error) manda `RELE 2 0` y `RELE 4 0` por una conexión nueva, con 3 intentos.
