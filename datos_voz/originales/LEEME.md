# datos_voz/originales/: grabaciones del celular (tal como llegan)

Los scripts solo leen esta carpeta, nunca la modifican. No está en el repositorio.

```
datos_voz/originales/
  Persona1/                 una carpeta por persona; el nombre en minúsculas es el de la persona
    persona1_A.m4a          bloque A: "Hola Doby" de varias formas
    persona1_B.m4a          bloque B: órdenes para Doby
    persona1_C.m4a          bloque C: habla libre (1 a 2 min)
    persona1_D.m4a          bloque D: frases para clonar la voz
    persona1_E.m4a          bloque E: lectura continua
    persona1_B_1.m4a, persona1_B_2.m4a   (si un bloque viene en varias partes)
```

- **Nombre:** el bloque es la primera parte del nombre que sea una sola letra de A a E, y la parte es el número final (`_1`, `_2`). Lo que no se pueda identificar con seguridad se lista y **no** se procesa.
- **Formatos aceptados:** `.m4a .mp3 .mpeg .wav .ogg .opus .aac .flac .mp4 .3gp .amr .webm`, a cualquier frecuencia y número de canales. Se leen con PyAV, sin FFmpeg.
- **Siguiente paso:** `py entrenamiento/validar_audios.py --persona persona1 [--listar]` o `--todos`. Ver `../procesados/LEEME.md`.
