# voz_cache_f5/: voces clonadas de los integrantes (F5-TTS)

Doby responde con la voz del integrante verificado (`VOZ_CLONADA = True`, `CARPETA_VOZ_CLONADA = "voz_cache_f5"` en `pc/config.py`). Son voces de personas reales, así que **no están en el repositorio**.

## Estructura (una carpeta por integrante enrolado)

El nombre de cada carpeta debe ser igual al de `modelos/hablantes/hablantes.json`, por ejemplo `persona1/`, `persona2/`…

```
voz_cache_f5/
  generacion.csv                      registro de todos los candidatos (lo escribe el generador)
  persona1/
    <clave>_<md5>.wav                 45 frases: las 44 de tts.FRASES + "generica" ("Listo.")
    _alternativas/<clave>_<md5>_v<n>.wav   otras versiones aprobadas (respaldo si falla la principal)
    _revisar_de_oido/<clave>_<md5>.wav     ninguna versión pasó el control con Whisper: falta aprobarla
    hora/hora_HHMM_<md5>.wav          las 1440 horas del día + hora/generacion.csv
    hora/_revisar_de_oido/            horas pendientes de aprobar de oído
```

- `<md5>` son los 8 primeros caracteres hexadecimales del MD5 del texto. Para las frases, el texto es el de `voz_clonada.texto(clave)`: igual que `tts.FRASES`, salvo `descansar`, que no dice «Doby».
- Las carpetas que empiezan con `_` (`_piloto/`, `_pruebas_duracion/`) son pruebas. Doby no las lee.

## Formato

WAV PCM, mono, **16 kHz, 16 bits**, con el procesado de `tts._pulir` (pico = `VOLUMEN` × 32767; `verificar_cobertura.py` lo comprueba).

## Cómo se genera (entorno `venv_f5`, GPU; ver `requirements_f5.txt`)

1. Referencias de cada integrante: `voz_comparacion_f5/referencias/LEEME.md`, anotadas en `entrenamiento/referencias_voz_f5.json` (copia de `referencias_voz_f5.ejemplo.json`).
2. Frases:
   `venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py [--persona persona1]`
   - Para cada frase hace 3 versiones con la referencia principal y hasta 3 reintentos con los respaldos.
   - Se aprueba la primera que Whisper transcribe con similitud ≥ 0.95. Si ninguna pasa, la mejor va a `_revisar_de_oido/`.
   - Para decidir de oído: `--aprobar persona1 <clave>` o `--rechazar persona1 <clave>`.
3. Horas (unos 70 min por persona):
   - `venv_f5\Scripts\python.exe entrenamiento/generar_hora.py --persona persona1`
   - De oído: `--aprobar persona1 HHMM` / `--rechazar persona1 HHMM`.
4. Comprobar: `py pruebas/verificar_cobertura.py` (debe dar 100 %; si a un integrante le falta una hora solo es AVISO).
