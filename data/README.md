# data/

- `catalog_index.json`: lo que la IA aprendió de las obras reales del museo (descripciones,
  embeddings y perfiles de cada maestro). Se genera en un PC con
  `python scripts/build_catalog_index.py` y se versiona aquí. No contiene claves ni fotos.

El servicio lo carga al arrancar (`CATALOG_INDEX_PATH`). Si no existe o no es válido, todo
funciona como antes, sin las recomendaciones por parecido visual.

## auctions_synthetic.csv — DATOS SINTÉTICOS

**Estas subastas no son reales.** MUSEO todavía no tiene historial de subastas, así que
`scripts/generate_auction_data.py` las simula para entrenar y evaluar el detector de pujas
sospechosas. Se generan con semilla fija (`--seed 2026`): el mismo comando da siempre el mismo
archivo.

- Una fila por puja, con el estado de la subasta justo antes (`current_bid_before`,
  `leader_before`) y la etiqueta `label`: `normal`, `shill` (puja inflada), `bot_burst`
  (ráfaga tipo bot), `huge_jump` (salto exagerado) o `new_account_high` (cuenta nueva con un
  monto muy alto). `is_suspicious` es 1 para todo lo que no es `normal`.
- Obras y precios base salen de `data/obras.csv` del frontend; postores, fechas y montos son
  inventados.
- No sirve para sacar conclusiones sobre compradores reales: solo para entrenar y probar.
