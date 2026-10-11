# Capturas

Las imágenes viven en `docs/screenshots/`. Esta página las describe y explica cómo
volver a generarlas o reemplazarlas por capturas reales de tu equipo.

## Hero

![Consola Tron de JudgeMan-Mike](screenshots/hero.gif)

`hero.gif` muestra la consola Tron en acción: el HUD con los gauges, una consulta
de diagnóstico y la propuesta de una acción.

## Consola Tron

| Archivo | Qué muestra |
|---------|-------------|
| `screenshots/tui-hud.png` | El HUD con reloj y gauges de CPU / RAM / disco. |
| `screenshots/tui-ports.png` | La salida de `/ports` con PID y proceso. |
| `screenshots/acciones-confirmacion.png` | La confirmación `y/N` antes de aplicar una acción. |

## Monitor web

| Archivo | Qué muestra |
|---------|-------------|
| `screenshots/monitor-web.png` | La interfaz web con "Cambios recientes" y "Diagnóstico del sistema". |

## Volver a generarlas

Las imágenes incluidas son **representaciones** de la interfaz (renderizadas a
partir de la misma paleta y los mismos textos del tema), pensadas para la
documentación del repositorio. Para sustituirlas por capturas reales:

1. Abre la consola en una terminal de al menos 100×30 columnas.
2. Ejecuta una consulta, por ejemplo `/ports`, y captura la pantalla.
3. Guarda el PNG en `docs/screenshots/` con el nombre de la tabla anterior.
4. Para el GIF, graba unos segundos con una herramienta de captura (ScreenToGif,
   Peek, asciinema + `agg`) y guárdalo como `hero.gif`.

Mantén el formato y los nombres para que los enlaces de esta página sigan
funcionando.
