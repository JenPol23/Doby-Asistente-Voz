# Guía para montar Doby en otro equipo

Esta guía es para quien clona el repositorio y quiere poner Doby a funcionar desde cero: otro PC, otra ESP32 y otra red. Los comandos son para **PowerShell**, desde la carpeta del proyecto.

> El repositorio **no trae** audios, huellas de voz ni modelos descargados. Hay que grabar y generar los suyos: cada carpeta de datos tiene un `LEEME.md` que dice qué va ahí.

---

## 1. Instalación desde cero

| Paso | Qué hacer | Cómo comprobarlo |
|---|---|---|
| 1 | Instalar **Python 3.11** (64 bits) para Windows, con el lanzador `py` | `py --version` → `Python 3.11.x` |
| 2 | Instalar torch con CUDA (ver README, **POR VERIFICAR** según tu GPU) | `py -c "import torch; print(torch.cuda.is_available())"` → `True` (o `False` si no hay GPU: Doby funciona en CPU, más lento) |
| 3 | `py -m pip install -r requirements.txt` | `py -c "import faster_whisper, speechbrain, sklearn, gtts, pygame, tzdata"` sin errores |
| 4 | Descargar ECAPA en `modelos/ecapa-voxceleb/` (README, sección «Modelos descargados») | `py -c "import sys; sys.path.insert(0,'entrenamiento'); import hablantes as h; h.cargar_modelo()"` sin errores |
| 5 | Whisper medium: se descarga solo la primera vez (necesita internet) | `py pruebas/prueba_escucha.py` (con la placa lista) carga «Whisper medium listo en …» |
| 6 | Instalar **MicroPython para ESP32-S3** en la placa (**POR VERIFICAR** la versión exacta usada; la sacas de la placa en Thonny con `import sys; sys.version`) | Thonny muestra el prompt `>>>` de la placa |
| 7 | Copiar `esp32/secretos.ejemplo.py` como `esp32/secretos.py`, con **tu** red WiFi de 2.4 GHz | El archivo existe y **no** aparece en `git status` |
| 8 | Subir a la placa con Thonny (clic derecho > «Subir a /»): `secretos.py` y `main.py` | Al reiniciar, la consola de Thonny dice `Doby listo en <IP>:5000` |
| 9 | Copiar esa IP en `IP_ESP32` de `pc/config.py` (línea 4) | `py pruebas/prueba_protocolo.py` responde PONG |
| 10 | Grabar, enrolar y generar voces (README, sección «Puesta en marcha», pasos 3 a 6) | `py pruebas/verificar_cobertura.py` → `RESULTADO: 100 %` |

Si no se van a usar voces clonadas, pon `VOZ_CLONADA = False` en `pc/config.py` (línea 49) y basta con `py pc/tts.py` (voz normal). Sin enrolamiento, pon `VERIFICAR_HABLANTE = False` (línea 33): Doby obedece a cualquiera.

## 2. Rutas, red e IP: qué se configura y dónde

| Qué | Dónde se cambia | Valor de ejemplo | Notas |
|---|---|---|---|
| Nombre y clave del WiFi | `esp32/secretos.py` (`RED`, `CLAVE`) | `"NombreDeMiRed"`, `"MiClaveWiFi123"` | Solo 2.4 GHz. **No se sube** al repositorio. |
| IP de la ESP32 | `pc/config.py:4` (`IP_ESP32`) | `"192.168.x.y"` | La imprime la placa al arrancar. Cambia si cambia la red. También la leen `pruebas/pc_prueba_mic.py` y `pc_prueba_voz.py`. |
| Puerto TCP | `pc/config.py:5` y `esp32/main.py:23` (`PUERTO`) | `5000` | Debe ser igual en los dos. |
| Relé → aparato (PC) | `pc/config.py:19` (`APARATOS`) | `"ventilador": 1` | Ver `GUIA_CAMBIOS.md`, receta 3. |
| Relé → GPIO (placa) | `esp32/main.py:27` (`PINES_RELE`) | `{1: 10, 2: 11, 3: 12, 4: 13}` | Ver `CONEXIONES.md`. |
| Modelo de intenciones | `modelos/base.joblib` y `base_info.json` | — | Viene en el repositorio. |
| Enrolamiento (huellas) | `modelos/hablantes/` | — | Se genera; no se sube. |
| Modelo ECAPA | `modelos/ecapa-voxceleb/` | — | Se descarga. |
| Modelo F5 | `modelos/f5-spanish/` | — | Se descarga; solo para generar voces. |
| Voz normal | `voz_cache/` y `voz_cache/hora/` | — | `py pc/tts.py`, `py entrenamiento/generar_hora.py --normal`. |
| Voces clonadas | `voz_cache_f5/<persona>/` (carpeta en `pc/config.py:51`) | — | Ver `voz_cache_f5/LEEME.md`. |
| Registros | `logs/` | `verificacion_<fecha>.csv`, `voz_<fecha>.csv` | Se crean solos. No se suben (tienen transcripciones y similitudes de voz). |

## 3. ¿El `main.py` de la placa es el del repositorio?

La placa ejecuta el `main.py` que tiene guardado, no el del PC. Para saber si es el actual:

1. **Comparar el archivo** (lo más seguro):
   - **Con Thonny:** Vista > Archivos. En «Dispositivo MicroPython» abre `main.py`, copia todo y compáralo con `esp32/main.py`. Por ejemplo, pégalo en `placa_main.py` y corre `fc.exe /N placa_main.py esp32\main.py`; si dice «no se encontraron diferencias», es el mismo.
   - **Con `mpremote`** (`py -m pip install mpremote`, **POR VERIFICAR** el puerto `COMx` en el Administrador de dispositivos):
     ```powershell
     py -m mpremote connect COM3 cp :main.py placa_main.py
     Get-FileHash placa_main.py, esp32\main.py
     ```
     Los dos hash deben ser iguales. Borra `placa_main.py` después; no lo subas.
2. **Por el comportamiento:** con la versión actual, al cerrar Doby la consola de la placa (Thonny) dice `PC desconectado. Si no vuelve en 15 s se apagan el cautin y la plancha.`. Las versiones viejas no tienen ese mensaje.

Si no es igual, súbelo de nuevo con Thonny y reinicia la placa (botón RST o Ctrl+D en Thonny).

## 4. Pruebas en orden

Ve en este orden y **no sigas** si un paso falla. Cierra Doby antes de cada prueba con la placa: la ESP32 atiende **un solo PC a la vez**.

### 4.1 Placa sola (sin 110 V conectado)

| Prueba | Cómo | Qué debe pasar |
|---|---|---|
| Montaje | En Thonny, ejecuta `pruebas/prueba_componentes.py` en la placa | Clic de cada relé (1 a 4), un tono por el parlante y números del micrófono que cambian al hablar. Si el número queda en 0, revisa VDD (3V3), GND, L/R y las soldaduras del INMP441. |
| Micrófono por WiFi | En la placa: `pruebas/esp32_prueba_mic.py` (Thonny). En el PC: `py pruebas/pc_prueba_mic.py` | Se graban 5 s en `grabacion.wav` y suenan en el PC |
| Parlante por WiFi | En la placa: `pruebas/esp32_prueba_parlante.py`. En el PC: `py pruebas/pc_prueba_voz.py` (usa gTTS: internet) | La frase suena en el PC y luego en el parlante |
| Firmware de Doby | Placa con `main.py` (y `secretos.py`). En el PC: `py pruebas/prueba_protocolo.py` | PONG, clic de los relés **1 a 3**, 3 s de micrófono en `pruebas/prueba_protocolo.wav` y un pitido |
| Voz y Whisper | `py pruebas/prueba_escucha.py` | Escucha 3 frases y muestra el texto de Whisper |

`esp32_prueba_mic.py` y `esp32_prueba_parlante.py` también importan `RED` y `CLAVE` de `secretos.py`: súbelo a la placa antes.

### 4.2 Relés sin carga (sin 110 V)

1. Placa con `main.py`. En el PC: `py pc/doby.py --texto` (sin micrófono ni verificación).
2. Escribe `hola doby prende el ventilador`, `apaga el ventilador`, `prende todo` y `apaga todo`.
3. Debe sonar el clic y encenderse el LED del relé correcto: ventilador 1, cautín 2, bombillo 3 y plancha 4. Si se enciende otro, revisa `APARATOS` (`pc/config.py:19`) y `PINES_RELE` (`esp32/main.py:27`).
4. Al cerrar con una línea vacía, la consola dice `Apagados al salir: cautin y plancha`.

### 4.3 Solo el bombillo a 110 V

1. **Enchufe desconectado.** Conecta solo el bombillo al relé 3, según [CONEXIONES.md](CONEXIONES.md#seguridad-eléctrica-110-v).
2. Revisa el cableado, conecta el enchufe y repite `prende el bombillo` / `apaga el bombillo` en `--texto`.
3. Después, en modo voz: `py pc/doby.py`, decir «Hola Doby» y luego «Prende la luz».

### 4.4 Todo

1. **Enchufe desconectado.** Conecta el ventilador (relé 1), el cautín (relé 2) y la plancha (relé 4). Pon el cautín y la plancha en sus soportes.
2. `py pruebas/verificar_cobertura.py` → 100 %.
3. `py pc/doby.py` y prueba con la voz de cada integrante enrolado:
   - «Hola Doby»
   - «Prende el cautín», «¿Qué está encendido?», «Apaga todo»
   - «Doby, ¿qué hora es?»
   - Una persona **no** enrolada debe recibir «No reconozco tu voz.».
4. **Seguridad:** con el cautín encendido, cierra Doby (Ctrl+C) y comprueba que se apaga.
   - Repite desconectando el PC de la red: la placa da al PC por perdido tras 60 s sin órdenes y apaga el cautín 15 s después (unos 75 s en total).
   - Si es la placa la que pierde el WiFi, lo apaga de inmediato.

Pruebas sin la placa (sirven después de cualquier cambio de código): `py pruebas/prueba_ordenes.py`, `py pruebas/prueba_firmware.py`.

## 5. Problemas comunes

| Síntoma (mensaje) | Causa probable | Qué hacer |
|---|---|---|
| Placa: `No se pudo. El punto de acceso esta encendido y en 2.4 GHz?` | Red de 5 GHz, nombre o clave mal escritos | Revisa `secretos.py`; en el celular, activa «banda 2.4 GHz» en el punto de acceso |
| PC: `No se pudo conectar a la ESP32 (intento N)` | IP distinta, PC en otra red, otra herramienta conectada a la placa | Mira la IP que imprime la placa y ponla en `pc/config.py:4`. Cierra otras pruebas o Thonny |
| `AVISO: Whisper no pudo usar la GPU (...). Uso la CPU con int8.` | torch sin CUDA o DLL de CUDA | Doby sigue en CPU (más lento). Revisa la instalación de torch |
| `!!  ERROR: FALTAN AUDIOS DE VOZ` | Faltan WAV en `voz_cache/` o `voz_cache_f5/` | `py pruebas/verificar_cobertura.py` dice cuáles; genéralos (ver los `LEEME.md`) |
| `AVISO: no se pudo cargar la verificacion de hablante (...)` | Falta `modelos/hablantes/` o `modelos/ecapa-voxceleb/` | Enrola (`GUIA_CAMBIOS.md`, receta 1) o pon `VERIFICAR_HABLANTE = False` |
| Doby dice «No reconozco tu voz» a un integrante muy seguido | Sala, micrófono o ruido distintos a los del enrolamiento | Mide con `py entrenamiento/probar_hablante.py --persona persona1` y re-enrola en el sitio (`GUIA_CAMBIOS.md`, receta 1) |
| Las frases no terminan (duran 8 s) o Doby escucha «solo» | El ruido supera el umbral de voz (ventilador encendido) | Pon un número fijo en `UMBRAL_MANUAL` (`pc/config.py:14`, por ejemplo 1500) |
| `Se perdio la conexion con el microfono (timed out)` | Atasco del WiFi | `py pruebas/diagnostico_mic.py` (con Doby cerrado) dice si es la red o la placa. Acerca el punto de acceso |
| `ZoneInfoNotFoundError: America/Bogota` | Falta `tzdata` en Windows | `py -m pip install tzdata` |
| `torchaudio.load` / FFmpeg al generar voces | torchaudio 2.11 necesita FFmpeg | Los scripts del repositorio leen con `soundfile`; no uses `torchaudio.load` |
| Un relé no apaga (aparato sigue encendido) | Relé pegado o cableado en NC | **Desconecta el enchufe** y revisa con el multímetro (`CONEXIONES.md`) |
| Doby responde «No te entendí» a órdenes claras | Whisper transcribió mal o la frase es nueva para el modelo | Mira en consola `Whisper: "..."` y `Modelo: ... (confianza ...)`. Si la frase es razonable, agrégala (`GUIA_CAMBIOS.md`, receta 4) |

## 6. Lista de verificación

**Antes de la primera prueba**
- [ ] `py --version` es 3.11 y `requirements.txt` se instaló sin errores.
- [ ] `modelos/ecapa-voxceleb/` existe (si se usa verificación).
- [ ] `esp32/secretos.py` tiene **tu** red; **no** está en el repositorio (`git status` no lo muestra).
- [ ] La placa tiene el `main.py` actual (sección 3).
- [ ] `IP_ESP32` en `pc/config.py:4` es la que imprime la placa.
- [ ] `py pruebas/prueba_ordenes.py` y `py pruebas/prueba_firmware.py` pasan.

**Voces y personas**
- [ ] Cada integrante tiene sus tomas en `datos_voz/inmp441/<persona>/` (15 A + 22 B).
- [ ] `modelos/hablantes/hablantes.json` lista a los integrantes correctos.
- [ ] `py pruebas/verificar_cobertura.py` da 100 %.

**Eléctrico (ver CONEXIONES.md)**
- [ ] Todo el cableado de 110 V se hizo **con el enchufe desconectado**.
- [ ] Cada relé usa COM–NO; en reposo, el aparato queda apagado.
- [ ] La corriente de cada aparato es menor que la nominal del relé.
- [ ] La ESP32 **no** está alimentada por USB y por la fuente a la vez.
- [ ] El cautín y la plancha están en sus soportes, lejos de cosas que se quemen.
- [ ] Hay un interruptor o regleta para cortar todo a mano.

**Funcionamiento**
- [ ] Relés sin carga: el relé de cada aparato es el correcto (4.2).
- [ ] Bombillo a 110 V enciende y apaga (4.3).
- [ ] Una persona no enrolada recibe «No reconozco tu voz.» y no enciende nada.
- [ ] Al cerrar Doby se apagan el cautín y la plancha; sin PC, la placa los apaga en 15 s.
- [ ] «Doby, ¿qué hora es?» dice la hora correcta.
