# modelos/hablantes/: enrolamiento de los integrantes (huellas de voz)

Doby (`pc/verificador.py`) carga esta carpeta para saber quién habla. Son **datos biométricos** de los integrantes: **nunca se suben** al repositorio.

| Archivo | Contenido |
|---|---|
| `centroides.npy` | Matriz float de N × 192: un centroide ECAPA (norma 1) por integrante, en el orden de `nombres` |
| `hablantes.json` | Ver el ejemplo de abajo |
| `clasificador.joblib` | Solo si el método elegido no es `coseno` (Doby solo acepta `coseno`) |

Ejemplo de `hablantes.json` con valores inventados:

```json
{
  "nombres": ["persona1", "persona2", "persona3"],
  "fecha": "AAAA-MM-DD HH:MM",
  "variante": "a+aum",
  "metodo": "coseno",
  "umbral_alto": 0.0,
  "umbral_bajo": 0.0,
  "preparar": {"version": 1, "corte_hz": 100, "rms_objetivo_dbfs": -20.0, "voz_minima_s": 0.5},
  "modelo": "modelos/ecapa-voxceleb (speechbrain/spkrec-ecapa-voxceleb)"
}
```

- `nombres` son los nombres de las carpetas de `datos_voz/inmp441/`. Deben coincidir con las carpetas de `voz_cache_f5/` y las claves de `entrenamiento/referencias_voz_f5.json` (plantilla: `referencias_voz_f5.ejemplo.json`).
- `umbral_alto` y `umbral_bajo` **se calculan con las voces del grupo**. No se copian de otro proyecto.
- `preparar.version` debe ser igual a `VERSION_PREPARAR` de `entrenamiento/hablantes.py`. Si no, Doby no carga la verificación.

**Cómo se genera** (después de grabar con `grabar_inmp441.py` y `grabar_ruido.py`):

```
py entrenamiento/evaluar_hablantes.py      # evalúa variantes y métodos y propone los umbrales (no incluido en el repositorio)
py entrenamiento/enrolar_hablantes.py      # escribe centroides.npy y hablantes.json
py entrenamiento/enrolar_hablantes.py --incluir-pruebas   # + tomas de probar_hablante.py --guardar (conserva los umbrales)
```

Si esta carpeta falta, Doby avisa y sigue **sin verificación de hablante**. También se puede poner `VERIFICAR_HABLANTE = False` en `pc/config.py`.
