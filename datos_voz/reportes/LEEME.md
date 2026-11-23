# datos_voz/reportes/: reportes de las grabaciones y de la verificación

Tienen nombres, transcripciones y similitudes de voz de los integrantes, así que no están en el repositorio.

| Archivo | Lo crea |
|---|---|
| `reporte_<persona>.md`, `resumen_<persona>.json`, `segmentos_<persona>.csv` | `py entrenamiento/validar_audios.py --persona <persona>` |
| `reporte_hablantes.md`, `hablantes/` (gráficas FAR/FRR, `division_semilla42.csv`, `pruebas_genuinas.csv`, `pruebas_impostores.csv`, `evaluacion.json`) | `py entrenamiento/evaluar_hablantes.py` (no incluido en el repositorio) |

`hablantes/evaluacion.json` es la entrada de `entrenamiento/enrolar_hablantes.py`: la variante, el método y los umbrales elegidos.
