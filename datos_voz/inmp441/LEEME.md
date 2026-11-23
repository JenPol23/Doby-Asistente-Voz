# datos_voz/inmp441/: tomas grabadas con el micrófono de la ESP32

Con estas tomas se enrola y evalúa la verificación de hablante (ECAPA). Se graban con la **misma captura que usa Doby**. No están en el repositorio.

```
datos_voz/inmp441/
  persona1/
    persona1_A_01.wav ... persona1_A_15.wav   bloque A: 15 "Hola Doby" (ventana de 3 s)
    persona1_B_01.wav ... persona1_B_22.wav   bloque B: 22 órdenes (ventana de 4 s)
    persona1_grabaciones.csv                  una fila por toma (pico, huecos, fecha)
  persona2/ ...
  impostor_01/      (opcional) personas que NO son del grupo: solo bloque A, solo para PROBAR
  _prueba/          prueba_<fecha>.wav de --prueba (no se usa para enrolar)
```

- El nombre de la carpeta (en minúsculas, sin tildes) es el nombre con que Doby enrola a la persona.
- Las carpetas que empiezan con `impostor` nunca entran al enrolamiento. Las que empiezan con `_` se ignoran.
- **Formato:** WAV PCM, mono, **16 kHz, 16 bits**, crudo: sin ganancia ni filtro, `int16 = round(audio × 32768)` después de `muestra >> 16` y quitar la media.
- Las frases de cada bloque salen de `datos/guion_voces/guion_voces.json`.

**Cómo se graba** (con la ESP32 encendida y Doby cerrado):

```
py entrenamiento/grabar_inmp441.py --prueba                         # 10 s para revisar el micrófono
py entrenamiento/grabar_inmp441.py --persona persona1 --bloque A
py entrenamiento/grabar_inmp441.py --persona persona1 --bloque B
py entrenamiento/grabar_inmp441.py --persona persona1 --bloque B --desde 7   # retomar en la frase 7
```

Después: `py entrenamiento/evaluar_hablantes.py` (no incluido en el repositorio) y `py entrenamiento/enrolar_hablantes.py` (ver `modelos/hablantes/LEEME.md`).
