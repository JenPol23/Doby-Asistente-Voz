# datos_voz/: grabaciones de voz y datos derivados

Aquí van las grabaciones de los integrantes y todo lo que sale de ellas. Son **datos personales y biométricos**: nada de esta carpeta se sube al repositorio, solo estos `LEEME.md`.

| Subcarpeta | Contenido | Lo crea |
|---|---|---|
| `inmp441/` | Tomas grabadas con el micrófono de la ESP32 (enrolar y evaluar la verificación) | `entrenamiento/grabar_inmp441.py` |
| `originales/` | Grabaciones del celular, tal como llegan (solo se leen) | los integrantes |
| `procesados/` | Grabaciones del celular cortadas en frases | `entrenamiento/validar_audios.py` |
| `ruido/` | Ruido de los aparatos con el INMP441 (aumento de datos y pruebas con ruido) | `entrenamiento/grabar_ruido.py` |
| `cache_hablantes/` | Caché de embeddings ECAPA (**huellas de voz**) | `entrenamiento/evaluar_hablantes.py` (no incluido en el repositorio) |
| `reportes/` | Reportes de validación y de la evaluación de hablantes | `validar_audios.py`, `evaluar_hablantes.py` |
| `pruebas_hablante/` | Tomas de calibración en el salón + `registro.csv` (la carpeta se crea sola) | `entrenamiento/probar_hablante.py --guardar` |

Cada subcarpeta tiene su `LEEME.md` con los nombres y formatos exactos.

Las frases que se leen en cada bloque (A: «Hola Doby», B: órdenes, C: habla libre, D: frases para clonar, E: lectura) están en `datos/guion_voces/guion_voces.json`.
