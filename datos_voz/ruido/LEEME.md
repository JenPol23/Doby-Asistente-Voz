# datos_voz/ruido/: ruido de los aparatos grabado con el INMP441

Se usa para el aumento de datos al enrolar y para evaluar la verificación con ruido (20, 10 y 5 dB). No está en el repositorio.

```
datos_voz/ruido/
  cuarto/                                   <lugar>
    ruido_cuarto_<condicion>_<nn>.wav
    ruido_cuarto.csv                        una fila por grabación (relés, niveles, fecha)
```

- **Condiciones:** `base`, `ventilador`, `bombillo`, `cautin`, `plancha`, `todos` y `murmullo` (voz de fondo desde un celular). `conjunto_hablantes.py` usa las de `CONDICIONES` (ventilador, murmullo, todos…).
- **Formato:** WAV PCM, mono, **16 kHz, 16 bits**, crudo (la misma captura que `grabar_inmp441.py`).
- **Cómo se graba** (ESP32 encendida, Doby cerrado; el script prende y apaga los relés):

```
py entrenamiento/grabar_ruido.py --lugar cuarto
py entrenamiento/grabar_ruido.py --lugar salon --seg 20
py entrenamiento/grabar_ruido.py --lugar cuarto --solo ventilador,todos
```

Nunca sobrescribe: cada toma nueva usa el siguiente `<nn>` libre.
