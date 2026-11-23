# voz_comparacion_f5/referencias/: clips de referencia para clonar cada voz (F5-TTS)

Son grabaciones reales de los integrantes, así que **no están en el repositorio**. `entrenamiento/generar_voces_f5.py` (y `generar_hora.py --persona`) las usa para clonar la voz.

## Qué va aquí

```
voz_comparacion_f5/referencias/
  persona1/
    persona1_refA1.wav    clip de voz
    persona1_refA1.txt    texto EXACTO de lo que se dice en el clip (UTF-8, una línea)
    persona1_refA2.wav / .txt
    persona1_refA3.wav / .txt
```

- **Clip:** WAV PCM **mono, 16 bits**, a la frecuencia original de la grabación (44.1 o 48 kHz sirven; F5 lo convierte).
  - Debe durar **6 a 12 s** de habla fluida, de una sola persona, sin música, ruido ni muletillas («eh», «mmm»).
  - Debe empezar y terminar en una pausa natural.
- **Texto:** la transcripción exacta del clip, con mayúsculas y signos. Si el texto no coincide con el audio, F5 genera mal.
- **Nombre:** libre, pero el `.wav` y el `.txt` deben llamarse igual. El nombre se anota en `entrenamiento/referencias_voz_f5.json`, que se crea copiando `entrenamiento/referencias_voz_f5.ejemplo.json`:

```json
{
  "persona1": ["persona1_refA1", "persona1_refA2", "persona1_refA3"],
  "persona2": ["persona2_refA2", "persona2_refA1", "persona2_refA3"]
}
```

El primer clip es la **referencia principal** y los otros dos son respaldos (se acepta de 1 a 3). La clave de cada persona debe ser igual a su nombre en `modelos/hablantes/hablantes.json`.

## Cómo hacer los clips sin los scripts de experimentos

Los clips originales se cortaron con un script de experimentos que no está en el repositorio. Se pueden hacer a mano:

1. Graba a cada integrante leyendo o hablando 1 a 2 minutos en un cuarto silencioso (celular o micrófono). Opcional: `py entrenamiento/validar_audios.py --persona persona1` corta y transcribe las grabaciones del celular puestas en `datos_voz/originales/Persona1/`.
2. Con un editor de audio (por ejemplo Audacity), corta 3 tramos de 6 a 12 s que suenen naturales y claros. Exporta cada uno como **WAV, mono, PCM de 16 bits**.
3. Escribe al lado un `.txt` con lo que se dice exactamente en cada tramo.
4. Anota los nombres en `entrenamiento/referencias_voz_f5.json`, con la referencia que mejor suene de primera.
5. Prueba con una sola frase: `venv_f5\Scripts\python.exe entrenamiento/generar_voces_f5.py --persona persona1 --frase saludo_1`. Escúchala con `py entrenamiento/escuchar_voz.py`. Si no se parece, cambia la referencia principal.
