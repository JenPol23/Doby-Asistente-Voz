# datos_voz/procesados/: grabaciones del celular cortadas en frases

No están en el repositorio. Las genera `validar_audios.py` a partir de `datos_voz/originales/`.

```
datos_voz/procesados/
  persona1/
    persona1_A_<nn>.wav, persona1_B_<nn>.wav, persona1_D_<nn>.wav   una frase cada uno (nn = número de frase del guion)
    persona1_C.wav, persona1_E.wav                                bloques largos, enteros
```

- **Formato:** WAV PCM, mono, **16 kHz, 16 bits**.
- **Cómo se genera:** `py entrenamiento/validar_audios.py --persona persona1` (o `--todos`). Usa el Whisper de Doby.
- Además escribe `datos_voz/reportes/reporte_persona1.md`, `resumen_persona1.json` y `segmentos_persona1.csv`. Con ese CSV se eligen los tramos para enrolar y para las referencias de voz.
