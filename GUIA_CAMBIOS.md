# Guía de cambios: recetas

Cómo adaptar Doby: otras personas, otras voces, otros aparatos y otras frases. Cada receta dice **qué archivo y qué línea tocar** (`archivo:línea`), **qué comando correr** y **cómo comprobar** que quedó bien. Los números de línea son los de esta versión del repositorio. Si cambian, busca el nombre de la constante.

Reglas generales:
- Después de cualquier cambio de código, corre `py pruebas/prueba_ordenes.py` y `py pruebas/prueba_firmware.py`. Usan una ESP32 falsa y deben pasar.
- Antes de arrancar Doby, corre `py pruebas/verificar_cobertura.py`. Debe dar 100 %.
- Ejemplos de nombres: `persona1`, `persona2`… Usa minúsculas, sin tildes ni espacios.

---

## Receta 1. Cambiar las personas que reconoce

Doby reconoce a quien esté en `modelos/hablantes/` (centroides + `hablantes.json`). Agregar, quitar o cambiar a alguien es **volver a enrolar**.

| Paso | Archivo:línea | Comando | Cómo comprobar |
|---|---|---|---|
| 1. Grabar (ESP32 encendida, Doby cerrado). Frases: `datos/guion_voces/guion_voces.json`; cantidades en `entrenamiento/grabar_inmp441.py:58` (`FRASES_ESPERADAS`) | — | `py entrenamiento/grabar_inmp441.py --persona persona4 --bloque A` y luego `--bloque B` | `datos_voz/inmp441/persona4/` tiene 15 `_A_` y 22 `_B_`. El informe de cada toma no dice «saturación» ni «voz muy baja» |
| 2. Quitar a alguien | `entrenamiento/conjunto_hablantes.py:69`: se ignoran las carpetas que empiezan con `_` | Renombra su carpeta `datos_voz/inmp441/persona2` → `_persona2` (no la borres) | — |
| 3. (Opcional) Ruido del sitio | `entrenamiento/grabar_ruido.py:53` (`CONDICIONES`) | `py entrenamiento/grabar_ruido.py --lugar salon` | Aparece `datos_voz/ruido/salon/` |
| 4. Evaluar y elegir umbrales | `entrenamiento/evaluar_hablantes.py` | `py entrenamiento/evaluar_hablantes.py` | `datos_voz/reportes/reporte_hablantes.md` y `hablantes/evaluacion.json` |
| 5. Enrolar | escribe `modelos/hablantes/hablantes.json` (`umbral_alto`, `umbral_bajo`) y `centroides.npy` | `py entrenamiento/enrolar_hablantes.py` | La consola dice `Guardado en modelos\hablantes: centroides.npy, hablantes.json (umbrales …)` |
| 6. Umbral de las órdenes con Doby despierto | `pc/config.py:39` (`UMBRAL_SESION`). Más alto: rechaza más órdenes del dueño y acepta menos órdenes de otros | Mide con `py entrenamiento/probar_hablante.py --persona persona4`: muestra la similitud y la decisión de una orden | En la toma del dueño debe salir «aceptada» y en la de otro «rechazada» |
| 7. Calibrar en el salón (opcional) | — | `py entrenamiento/probar_hablante.py --persona persona4 --guardar` y luego `py entrenamiento/enrolar_hablantes.py --incluir-pruebas` (conserva los umbrales) | — |
| 8. Su voz de respuesta | `voz_cache_f5/persona4/` | Receta 2b, o `VOZ_CLONADA = False` (`pc/config.py:49`) | `py pruebas/verificar_cobertura.py` |

> ⚠️ `entrenamiento/evaluar_hablantes.py` **no está en este repositorio**, y `enrolar_hablantes.py` lo importa. Sin él, los pasos 4 y 5 no corren.

Otros ajustes de la verificación:
- **Verificar solo el «Hola Doby»**, no cada orden: `VERIFICAR_ORDENES = False` (`pc/config.py:34`).
- **Ignorar en silencio a los desconocidos** en vez de decir «No reconozco tu voz»: `MODO_RECHAZO = "silencio"` (`pc/config.py:35`).
- **Desactivar la verificación:** `VERIFICAR_HABLANTE = False` (`pc/config.py:33`). Doby obedece a cualquiera.
- **Tiempo para repetir en la zona gris:** `SEG_REPETIR` (`pc/verificador.py:24`, 15 s). **Voz mínima para verificar:** `VOZ_MINIMA` (`entrenamiento/hablantes.py:35`, 0.5 s).

**Comprobar al final:** arranca `py pc/doby.py` y busca la línea `Integrantes: persona1, persona2, …`. Cada decisión queda en `logs/verificacion_<fecha>.csv`, con similitudes, umbrales y decisión.

---

## Receta 2. Cambiar las voces de respuesta

### 2a. Voz normal (gTTS): fácil

Es la voz para quien no está verificado, o para todos con `VOZ_CLONADA = False` (`pc/config.py:49`).

| Qué | Archivo:línea | Comando | Cómo comprobar |
|---|---|---|---|
| Acento (dominio de Google) | `pc/tts.py:116`: `gTTS(texto, lang="es", tld="com.mx")`. Por ejemplo, `tld="es"` (España) o `"com.co"` (**POR VERIFICAR** que gTTS acepte ese dominio) | Los archivos se llaman por el **texto**, no por el acento: **mueve** antes los WAV viejos de `voz_cache/` a otra carpeta. Luego `py pc/tts.py` y `py entrenamiento/generar_hora.py --normal` | `py pruebas/verificar_cobertura.py`. Escucha con `py pruebas/prueba_voz_doby.py` (las reproduce por la ESP32) |
| Texto de una respuesta | `pc/tts.py:64` (`_crear_frases`). Por ejemplo, `"saludo_1"` en la línea 66. Para la voz clonada sin «Doby»: `pc/voz_clonada.py:43` (`TEXTOS_CLONADOS`) | `py pc/tts.py` genera solo lo que falta (el nombre lleva el MD5 del texto) | `verificar_cobertura.py` |
| Volumen | `pc/config.py:9` (`VOLUMEN`, máximo 0.5 para el parlante de 1.5 W) | Hay que **regenerar todas** las voces, también las clonadas: `verificar_cobertura.py` exige que el pico sea `VOLUMEN × 32767` | `verificar_cobertura.py` |

La hora con la voz normal: el texto sale de `pc/hora.py:61` (`texto`). Si cambias el formato, regenera las 1440 con `generar_hora.py --normal` (unos 25 min y necesita internet).

### 2b. Voz clonada de cada integrante (F5-TTS): difícil y opcional

Necesita GPU, el entorno `venv_f5` (`requirements_f5.txt`) y el modelo `modelos/f5-spanish/`. Si no se quiere, basta con `VOZ_CLONADA = False`.

| Paso | Archivo | Comando | Cómo comprobar |
|---|---|---|---|
| 1. Clips de referencia (6 a 12 s + `.txt` exacto) | `voz_comparacion_f5/referencias/persona1/` (ver su `LEEME.md`) | a mano (Audacity) o con `py entrenamiento/validar_audios.py` para cortar | — |
| 2. Anotarlos | `entrenamiento/referencias_voz_f5.json` (copia de `referencias_voz_f5.ejemplo.json`) | — | Las claves son los nombres de `hablantes.json` |
| 3. Prueba con una frase | — | `venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py --persona persona1 --frase saludo_1` | Escúchala: `py entrenamiento/escuchar_voz.py` |
| 4. Todas las frases | — | `venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py --persona persona1` | Resumen en consola y `voz_cache_f5/generacion.csv` |
| 5. Revisar de oído | `voz_cache_f5/persona1/_revisar_de_oido/` | `… generar_voces_f5.py --aprobar persona1 <clave>` o `--rechazar persona1 <clave>` | La carpeta queda vacía |
| 6. Las 1440 horas (unos 70 min) | `voz_cache_f5/persona1/hora/` | `venv_f5\Scripts\python.exe entrenamiento/generar_hora.py --persona persona1` | `verificar_cobertura.py`: `persona1 hora 1440/1440 OK` |

Voz para quien no está verificado: `VOZ_POR_DEFECTO` (`pc/config.py:50`). `None` usa la voz normal; también puede ser el nombre de un integrante.

---

## Receta 3. Cambiar o renombrar los aparatos de cada relé

Ejemplo: el relé 4 deja de ser la «plancha» y pasa a ser una «lampara». Toca **todos** los puntos de la tabla: el nombre del aparato es la clave de las frases, del modelo y de las pruebas.

| # | Qué | Archivo:línea | Notas |
|---|---|---|---|
| 1 | Nombre → número de relé | `pc/config.py:19` (`APARATOS`) | Clave en minúsculas y **sin tilde** (`"lampara": 4`). El orden de la lista es el orden de las frases de estado |
| 2 | ¿Se calienta? | `pc/config.py:28` (`CALIENTES`) y `:29` (`APAGADO_AUTOMATICO`) | Si deja de calentarse, sácalo de `CALIENTES` |
| 3 | Pines y seguridad en la placa | `esp32/main.py:27` (`PINES_RELE`, relé → GPIO) y `:30` (`CALIENTES`, **números de relé**) | Debe coincidir con el paso 2. **Súbelo a la placa** con Thonny |
| 4 | Cómo se dice | `pc/tts.py:35` (`NOMBRES`, para tildes: `"lampara": "lámpara"`) y `:36` (`FEMENINOS`: «la lámpara», «encendida») | Las frases se arman solas desde `APARATOS` (`pc/tts.py:64`) |
| 5 | Palabras que lo nombran | `pc/doby.py:57` (`SINONIMOS`). Palabras de relleno: `:52` (`RELLENO`). Implícitos («calor» → ventilador): `:78` (`RAICES_IMPLICITAS`) | Las palabras van normalizadas (sin tildes, minúsculas) |
| 6 | Frases de entrenamiento | `entrenamiento/generar_sinteticas.py:36` (`APARATOS`), `:46` (`CONTEXTOS_ENCENDER`), `:54` (`IMPLICITOS_ENCENDER`), `:61` (`CONTEXTOS_APAGAR`), `:69` (`IMPLICITOS_APAGAR`) | También `datos/generadas.csv` y `datos/frases_demo.txt` si nombran el aparato viejo |
| 7 | Pruebas y herramientas | `pruebas/prueba_ordenes.py` (casos con el nombre), `pruebas/prueba_componentes.py:28` (`NOMBRES_RELE`), `entrenamiento/grabar_ruido.py:53` (`CONDICIONES`) | — |

**Comandos, en orden:**

```powershell
py entrenamiento/generar_sinteticas.py                      # datos/sinteticas.csv
py entrenamiento/preparar_datos.py                          # datos/train.csv y test.csv (necesita datos/massive/es-ES.jsonl: ver README)
py entrenamiento/entrenar_base.py --candidato candidato_lampara   # NO reemplaza el modelo en uso
py entrenamiento/probar_modelo.py "prende la lámpara" "apaga la lámpara" "la lámpara"
# si el candidato está bien: copiar modelos\candidato_lampara\base.joblib y base_info.json a modelos\
py pc/tts.py                                                # respuestas habladas nuevas (voz normal; internet)
venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py   # (opcional) voces clonadas de las frases nuevas
py pruebas/verificar_cobertura.py
py pruebas/prueba_ordenes.py
```

**Cómo comprobar:**
- En `resultados/candidato_lampara/base_metricas.txt`, la accuracy y el F1 macro no deben bajar mucho respecto a `resultados/base_metricas.txt` (0.9776 / 0.9759), y la demo debe quedar completa.
- Con `probar_modelo.py`, las órdenes con verbo deben salir con confianza ≥ 0.5 y la frase «la lámpara» sola debe quedar < 0.5.
- Después: `py pc/doby.py --texto`, escribe «hola doby prende la lámpara» y comprueba que suena el clic del relé correcto (`GUIA_PARA_OTROS.md`, 4.2).

Para **solo mover un aparato a otro relé**, sin cambiar el nombre, basta con los pasos 1, 2 y 3. Sin reentrenar ni regenerar voces.

---

## Receta 4. Agregar frases o intenciones

### 4a. Más frases para una intención que ya existe

Por ejemplo, Doby no entiende «dale luz».

| Paso | Archivo | Comando |
|---|---|---|
| 1. Ver qué entiende hoy | — | `py entrenamiento/probar_modelo.py "dale luz"` |
| 2. Agregar filas `texto,intencion,origen` | `datos/generadas.csv` (`origen` = `generada`) o un `datos/propias.csv` nuevo (`origen` = `propia`; gana ante duplicados) | — |
| 3. Rehacer los datos y entrenar un candidato | — | `py entrenamiento/preparar_datos.py`, luego `py entrenamiento/entrenar_base.py --candidato candidato_frases` |
| 4. Comprobar y adoptar | `resultados/candidato_frases/base_metricas.txt` | `py entrenamiento/probar_modelo.py "dale luz"`; si está bien, copia el candidato a `modelos/`; después `py pruebas/prueba_ordenes.py` |

Las intenciones válidas están en `entrenamiento/preparar_datos.py:44` (`INTENCIONES`). Las filas con otra intención se descartan sin error.

### 4b. Una intención nueva

Por ejemplo, `chiste`: «Doby, cuéntame un chiste».

| # | Qué | Archivo:línea |
|---|---|---|
| 1 | Declararla | `entrenamiento/preparar_datos.py:44` (`INTENCIONES`) |
| 2 | Ejemplos (decenas de frases distintas) | `datos/generadas.csv` o `datos/propias.csv`. Si quieres plantillas: una familia en `entrenamiento/generar_sinteticas.py` (las familias empiezan en la línea 150) |
| 3 | Qué hace Doby | `pc/doby.py:432` (`ejecutar`): agregar `elif intencion == "chiste": self.decir("chiste")` |
| 4 | Qué dice | `pc/tts.py:64` (`_crear_frases`): `frases["chiste"] = "…"`. **Sin la palabra «Doby»**: si no, `pc/voz_clonada.py` se niega a cargar |
| 5 | Demo y pruebas | `datos/frases_demo.txt` (`frase;intencion`) y un caso en `pruebas/prueba_ordenes.py` |

Comandos: los de la receta 3, desde `preparar_datos.py`. Si usas plantillas, empieza por `generar_sinteticas.py`. Después, `py pc/tts.py` para la frase nueva y `verificar_cobertura.py`.

### 4c. Una regla fija (sin el clasificador)

Sirve para frases exactas, como «qué hora es». La regla va en `pc/doby.py`, dentro de `procesar` (`pc/doby.py:290`), junto a `es_encender_todo` y `es_que_hora` (líneas 338-343). La función de ejemplo es `es_que_hora` (`pc/doby.py:182`). No hace falta reentrenar. Agrega un caso en `pruebas/prueba_ordenes.py`.

Otros ajustes:
- **Palabra de activación:** `pc/doby.py:30` (`VARIANTES_DOBY`).
- **Confianza mínima del modelo:** `pc/doby.py:27` (`UMBRAL` = 0.5).

---

## Tabla rápida

| Quiero cambiar… | Receta | Archivos | Comando principal |
|---|---|---|---|
| Agregar o quitar una persona | 1 | `datos_voz/inmp441/<persona>/`, `modelos/hablantes/` | `grabar_inmp441.py` → `evaluar_hablantes.py` → `enrolar_hablantes.py` |
| Qué tan estricto es con las órdenes | 1 | `pc/config.py:39` (`UMBRAL_SESION`) | `py entrenamiento/probar_hablante.py --persona persona1` |
| Que no verifique la voz | 1 | `pc/config.py:33` | — |
| Acento o texto de la voz normal | 2a | `pc/tts.py:116`, `pc/tts.py:64` | `py pc/tts.py` |
| Volumen | 2a | `pc/config.py:9` | regenerar todas las voces + `verificar_cobertura.py` |
| Voz clonada de un integrante | 2b | `voz_comparacion_f5/referencias/`, `entrenamiento/referencias_voz_f5.json` | `venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py --persona X` |
| Sin voces clonadas | 2b | `pc/config.py:49` (`VOZ_CLONADA = False`) | — |
| Mover un aparato a otro relé | 3 | `pc/config.py:19`, `esp32/main.py:27` y `:30` | subir `main.py` a la placa |
| Cambiar o renombrar un aparato | 3 | `pc/config.py:19`, `pc/tts.py:35-36`, `pc/doby.py:57`, `entrenamiento/generar_sinteticas.py:36-71`, `esp32/main.py` | `generar_sinteticas` → `preparar_datos` → `entrenar_base --candidato` → `pc/tts.py` |
| Tiempo de apagado automático | 3 | `pc/config.py:29`; en la placa `esp32/main.py:31-32` | subir `main.py` |
| Que entienda una frase más | 4a | `datos/generadas.csv` | `preparar_datos` → `entrenar_base --candidato` |
| Una intención nueva | 4b | `entrenamiento/preparar_datos.py:44`, `pc/doby.py:432`, `pc/tts.py:64`, `datos/*.csv` | `preparar_datos` → `entrenar_base --candidato` → `pc/tts.py` |
| Una frase fija sin modelo | 4c | `pc/doby.py:182`, `pc/doby.py:338-343` | `py pruebas/prueba_ordenes.py` |
| La palabra «Doby» | 4c | `pc/doby.py:30` | `py pruebas/prueba_ordenes.py` |
| IP o red | — | `pc/config.py:4`, `esp32/secretos.py` | ver `GUIA_PARA_OTROS.md` |
