# voz_cache/hora/: la hora con la voz normal (gTTS)

Doby dice la hora con esta voz cuando no hay un integrante verificado, o cuando a la voz clonada del integrante le falta esa hora. Si falta aquí, Doby se queda en silencio, así que **esta carpeta debe estar completa**. Los audios **no están en el repositorio**.

- **Archivos:** `hora_HHMM_<md5>.wav`, uno por minuto del día: **1440** (de `hora_0000_…` a `hora_2359_…`).
  - `HHMM` es la hora en 24 h.
  - `<md5>` son los 8 primeros caracteres hexadecimales del MD5 del texto de `hora.texto(h, m)` (`pc/hora.py`), por ejemplo «Son las nueve y veintitrés de la noche.».
- **Formato:** WAV PCM, mono, **16 kHz, 16 bits**, con el mismo procesado que `voz_cache/` (`tts._pulir`).
- **Registro:** `generacion.csv` (una fila por frase con la transcripción de Whisper).
- **Cómo se genera** (internet; una petición por segundo, unos 25 min; se puede retomar):
  `py entrenamiento/generar_hora.py --normal`
- **Comprobar:** `py pruebas/verificar_cobertura.py`
