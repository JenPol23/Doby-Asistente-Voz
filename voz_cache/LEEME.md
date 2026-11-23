# voz_cache/: voz normal de Doby (gTTS)

Doby usa esta voz cuando no hay un integrante verificado («No reconozco tu voz.», modo texto, etc.). Los audios **no están en el repositorio**: se generan.

- **Archivos:** `<clave>_<md5>.wav`, uno por cada frase de `tts.FRASES` (`pc/tts.py`; 44 frases con los 4 aparatos).
  - `<clave>` es la clave de la frase (`saludo_1`, `encendi_ventilador`, `estado_bombillo_plancha`…).
  - `<md5>` son los 8 primeros caracteres hexadecimales del MD5 del texto de la frase en UTF-8. Si cambia el texto, cambia el nombre.
- **Formato:** WAV PCM, mono, **16 kHz, 16 bits**.
  - Procesado de `tts._pulir`: pasa-altos de 200 Hz, pico = `VOLUMEN` × 32767 (`pc/config.py`), rampas de 10 ms y 0.3 s de silencio al final.
- **Cómo se genera** (necesita internet una sola vez): `py pc/tts.py`
- La subcarpeta `hora/` tiene la voz normal de «¿qué hora es?» (ver `hora/LEEME.md`).
- `_retirados_carro/` (si existe) guarda audios de un aparato que ya no se usa. Doby no la lee.
