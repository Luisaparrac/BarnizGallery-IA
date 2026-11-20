# data/

- `catalog_index.json`: lo que la IA aprendió de las obras reales del museo (descripciones,
  embeddings y perfiles de cada maestro). Se genera en un PC con
  `python scripts/build_catalog_index.py` y se versiona aquí. No contiene claves ni fotos.

El servicio lo carga al arrancar (`CATALOG_INDEX_PATH`). Si no existe o no es válido, todo
funciona como antes, sin las recomendaciones por parecido visual.
