# datos_voz/cache_hablantes/: caché de embeddings ECAPA (huellas de voz)

- **Archivo:** `embeddings.joblib`, un diccionario `{"firma": ..., "datos": ...}` con el embedding ECAPA (vector de 192, norma 1) de cada toma y de cada mezcla con ruido.
- **Son huellas de voz** (datos biométricos): **nunca se suben** al repositorio.
- **Cómo se genera:** `py entrenamiento/evaluar_hablantes.py` (no incluido en el repositorio). Se rehace solo si cambian `preparar()` o los ruidos; se puede borrar sin problema.
- Doby no lo usa: Doby carga `modelos/hablantes/`.
