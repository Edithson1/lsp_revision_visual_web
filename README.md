# Revisión visual LSP

Web local para comparar videos originales y simulados de Lengua de Señas Peruana
(LSP), comprobar efectos visuales y registrar una revisión humana. Se abre en
`http://127.0.0.1:8765`; trabaja con archivos de la propia PC.

El repositorio incluye solo código, pruebas y documentación. Los videos, listas,
plantillas y clasificaciones se incorporan localmente y no se suben a GitHub.

## Qué hacía

Se creó para revisar 38 registros de un CSV de 290, asociados a una salida de
553 videos individuales del simulador:

| Registros `n` | Efecto | Resultados de la entrega |
| --- | --- | --- |
| 1–9 | Gafas | `coincide`, `no coincide` |
| 50–53 | Objeto en mano | `coincide`, `no coincide` |
| 104–128 | Desenfoque | `correcto`, `caja fija`, `no se nota`, `otro` |

`n` identifica el registro, no la fila física de Excel. También permite explorar
train, val, test y efectos combinados; las clasificaciones adicionales se exportan
aparte. Se revisa el efecto, no la seña ni a la persona.

La aplicación no decide D48/D49 ni modifica los videos del dataset. Si otro proceso
reemplaza un video, la revisión y la bitácora deben identificar la versión evaluada.

## Requisitos

- Python **3.10 o posterior**. El servidor usa solo la biblioteca estándar.
- FFmpeg con `libx264` y PNG. La ruta de compatibilidad antigua requiere `libvpx-vp9`.
- Un navegador moderno con H.264 y JavaScript.
- Los archivos privados de revisión y el dataset local.
- Node.js 18 o posterior solo para ejecutar las pruebas JavaScript.

No se necesita npm, compilación del frontend ni base de datos. El servidor no instala
paquetes ni descarga ejecutables. `dist/` contiene los archivos estáticos de la web
y **sí se versiona**.

## Preparar los archivos locales

Coloca el repositorio junto a las carpetas del proyecto, o indica su ubicación con
`--project`:

```text
carpeta_de_trabajo/
├── lsp_revision_visual_web/  # este repositorio, también puede llamarse revision_visual_web
│   ├── server.py
│   ├── dist/
│   └── data/                # archivos privados, ignorados por Git
├── originales_organizados/
│   ├── originales_train/<glosa>/*.mp4
│   ├── originales_val/<glosa>/*.mp4
│   └── originales_test/<glosa>/*.mp4
└── simulador_escenarios_lsp/salidas/
    ├── prueba_single_original_sin_perdida/<glosa>/*.mp4
    ├── editados_train/<glosa>/*.mp4
    ├── editados_val/<glosa>/*.mp4
    └── editados_test/<glosa>/*.mp4
```

Incorpora `data/lista_revision_visual_2026-11-14.csv` y, para exportar XLSX,
`data/plantilla_revision.xlsx`. También pueden estar en otras carpetas.
[El esquema del CSV y la plantilla](data/README.md) detalla su formato.
Una copia recién clonada necesita esos datos antes de iniciar la aplicación.

## Ejecutar

Desde la carpeta del repositorio:

```powershell
python server.py --open
```

La carpeta de proyecto predeterminada es la carpeta padre del repositorio.
Para usar otra disposición:

```powershell
python server.py --project "X:\datos\proyecto_lsp" --csv "X:\datos\revision\lista.csv" --template "X:\datos\revision\plantilla.xlsx" --ffmpeg "X:\herramientas\ffmpeg.exe" --open
```

FFmpeg se busca en este orden: `--ffmpeg`, variable `LSP_FFMPEG`, ejecutable local
de `simulador_escenarios_lsp/.venv/Lib/site-packages/imageio_ffmpeg/binaries/` y `PATH`.
`--port` cambia el puerto y `--review-file` permite usar otro JSON de clasificaciones.

En Windows puedes abrir `INICIAR_REVISION_VISUAL.bat` o ejecutar:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\iniciar.ps1 -ProjectPath "X:\datos\proyecto_lsp" -NoBrowser
```

El lanzador también acepta `-Port`, `-CsvPath`, `-TemplatePath` y `-Ffmpeg`.
Busca Python mediante `py -3`, el entorno del simulador y el `PATH`, con un respaldo
opcional del runtime local de Codex. No necesita una ruta de usuario concreta.
Inicia el servidor en segundo plano y reutiliza la instancia compatible del proyecto.
El servidor iniciado desde una terminal se detiene con Ctrl+C. Después de actualizar
código, reinicia la instancia y recarga la página con Ctrl+F5.

## Revisar y entregar

1. Abre **Solicitados en el README** para los 38 registros de la entrega.
2. Elige el original organizado o la **Base del simulador** como referencia.
   La base permite aislar el efecto con el mismo fondo y luz.
3. Usa **Reproducción fluida** para el movimiento y **Fotograma exacto** para detalles.
4. Selecciona resultado, nombre y fecha; explica las incidencias. En niveles 2/3,
   `no se nota` es un resultado permitido.
5. Pulsa **Guardar y siguiente**. Un borrador no cuenta como revisión guardada.
6. Exporta XLSX o CSV. La entrega conserva los 290 registros y completa solo los 38.
   Para los demás, utiliza **Clasificaciones ampliadas**.

**Versión del simulado** distingue las pruebas individuales del editado completo;
cambiar de versión cambia el registro que se clasifica. **Antes de la corrección**
solo aparece si el proyecto contiene el manifiesto local y su respaldo.
En el flujo original se utilizó para DEBAJO_2, registro 114; el repositorio no contiene
esos videos ni manifiestos. `/?n=114&frame=51&view=exact` abre ese registro alrededor
de 1,70 s cuando están disponibles sus datos. `frame` comienza en cero.

Atajos fuera de los campos: Espacio reproduce/pausa; 1–5 eligen resultado;
flechas izquierda/derecha navegan; Ctrl+Enter guarda y avanza.
La fecha inicial usa America/Lima.

## Cómo lo hacía

- **Catálogo:** lee el CSV y las carpetas conocidas del simulador. Vincula originales
  por conjunto, nombre y glosa; no asigna automáticamente una coincidencia ambigua.
  Mantiene visibles los casos cuyos archivos faltan.
- **Vista fluida:** FFmpeg genera una vista H.264 YUV420, CRF 10 y color BT.709,
  sin reducir dimensiones. Comprueba conteo y duración. La caché se identifica por
  SHA256 del archivo y versión del conversor y se limita a 512 MB, salvo el archivo
  activo si por sí solo excede ese tamaño. Es una vista comprimida.
- **Fotograma exacto:** decodifica el cuadro del archivo fuente y lo entrega como
  PNG RGB sin pérdida. Permite 100 % y 200 % con desplazamiento sincronizado.
  Pulsar una zona de la imagen ajustada la amplía. La caché en memoria se limita
  a 40 MB, salvo que un solo fotograma exceda ese tamaño.
- **Sincronización:** espera ambos videos, alinea el arranque y repite la pareja.
  Corrige pequeños desvíos con ajustes suaves de velocidad. Los pasos utilizan el
  FPS de la pista, incluidas tasas fraccionarias como 30000/1001.
- **Guardado:** escribe `data/revisiones.json` mediante un temporal y conserva la
  copia anterior. Los borradores pendientes usan localStorage del navegador.
- **Exportación:** incorpora los resultados al CSV original o a una copia en memoria
  de la plantilla XLSX. No escribe sobre la plantilla ni sobre la lista original.

El servidor escucha solo en `127.0.0.1`, soporta rangos HTTP y verifica el origen
de las escrituras. Se diseñó para una PC de confianza; no tiene autenticación para
exponerlo como servicio en Internet. Usar la aplicación no sube archivos a la nube.

## Estructura del código

| Archivo | Responsabilidad |
| --- | --- |
| `server.py` | Catálogo, medios, cachés, persistencia y exportaciones |
| `dist/app.js` | Filtros, formularios, detalle y navegación |
| `dist/playback.js` | Reproducción coordinada y avance por fotogramas |
| `dist/index.html`, `dist/styles.css` | Interfaz |
| `iniciar.ps1`, `INICIAR_REVISION_VISUAL.bat` | Arranque en Windows |
| `tests/test_portable.py` | Pruebas con datos ficticios temporales |
| `tests/test_app.py` | Integración opcional con los datos reales locales |
| `tests/test_playback.cjs` | Sincronización con reproductores simulados |

## Pruebas

Sin datos privados:

```powershell
python -m unittest discover -s tests -v
node --test tests/test_playback.cjs
```

Las pruebas de integración se omiten por defecto. Con la estructura habitual,
los archivos privados en `data/`, los videos y FFmpeg disponibles:

```powershell
$env:LSP_INTEGRATION = '1'
python -m unittest discover -s tests -v
Remove-Item Env:LSP_INTEGRATION
```

Comprueban correspondencias, persistencia, exportación, rangos HTTP, duración de la
vista fluida e igualdad RGB de un cuadro exacto. Usan revisiones temporales.

## Qué se publica

El `.gitignore` usa una lista permitida de código, lanzadores, pruebas y guías.
Excluye videos, capturas de personas, listas CSV, libros Excel, revisiones, cachés,
diagnósticos, logs, modelos, entornos virtuales y archivos comprimidos.
Para incorporar un módulo nuevo, actualiza también esa lista.

Antes de un commit revisa `git status --short` y `git diff --cached --stat`.
No fuerces datos con `git add -f`: `.gitignore` no elimina archivos ya versionados.

## Problemas habituales

- **Falta el CSV:** incorpora la lista privada o utiliza `--csv`.
- **Faltan videos:** comprueba `--project`, las carpetas y los nombres del CSV.
- **Falta FFmpeg o un códec:** configura `--ffmpeg` o `LSP_FFMPEG`.
- **La primera apertura tarda:** espera la preparación de ambas vistas; luego se reutiliza la caché.
- **El efecto suave no se distingue:** usa Fotograma exacto al 100 % o 200 %.
- **Falla la exportación XLSX:** proporciona una plantilla compatible con `--template`.
- **Puerto ocupado:** usa otro puerto o detén la instancia anterior de esta aplicación.
