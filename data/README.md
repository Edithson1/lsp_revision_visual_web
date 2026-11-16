# Archivos locales de revisión

Esta carpeta contiene únicamente esta guía en Git. Los datos se incorporan de forma local:

- `lista_revision_visual_2026-11-14.csv`: lista original, UTF-8, con sus 290 registros.
- `plantilla_revision.xlsx`: plantilla compatible para exportar el Excel oficial.
- `README_revision_visual.md`: instrucciones originales de la revisión, opcional para el servidor.

También puedes usar `--csv` y `--template` para leer los dos primeros desde otra carpeta.

El CSV debe conservar estas columnas, en este orden:

```text
n,subconjunto,familia,original,archivo,aviso_simulador,prioridad_simulador,fotogramas_con_efecto_pct,estado_conocido,que_mirar,resultado,revisado_por,fecha,observacion
```

La plantilla XLSX debe conservar la primera hoja con encabezados en la fila 1,
los 290 registros en las filas 2–291 y las cuatro columnas editables en K:N:
`resultado`, `revisado_por`, `fecha`, `observacion`. El exportador modifica esas
celdas sobre una copia en memoria; no escribe sobre la plantilla. Sin plantilla,
las exportaciones CSV y JSON siguen disponibles; la exportación XLSX informa del archivo faltante.

El servidor genera aquí `revisiones.json`, su copia anterior, registros de arranque
y `cache_reproduccion/`. El `.gitignore` los excluye junto con todos los datos de entrada.
Los borradores pendientes se guardan en el almacenamiento local del navegador.
