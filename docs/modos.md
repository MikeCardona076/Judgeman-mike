# Modos de trabajo

La sesión de chat siempre está en uno de tres modos. El modo decide qué contexto
del sistema se adjunta y cómo interpreta el modelo tu pregunta. En los tres casos
el flujo es el mismo: reunir evidencia de solo lectura, interpretar y, si hace
falta, **proponer** acciones de un catálogo cerrado.

## `diagnose` (por defecto)

Pensado para problemas del equipo: un puerto que no responde, un servicio caído,
algo que consume toda la CPU o la RAM, un arranque lento.

- Adjunta el **bundle completo**: puertos, procesos con más carga, conexiones
  salientes, arranque automático, servicios detenidos, firewall y `hosts`/proxy.
- Úsalo con preguntas como *"el puerto 3000 no responde"* o *"¿qué consume toda
  la CPU?"*.

## `security`

Centrado en amenazas. Combina el estado de la red con el análisis de contenido.

- Adjunta un **bundle reducido**: puertos a la escucha, conexiones salientes y
  servicios relevantes.
- Analiza texto que pegues o archivos que abras con `/file` buscando indicadores
  de riesgo (persistencia, conexiones sospechosas, cambios en `hosts`/DNS/proxy,
  exposiciones en el firewall).

## `file`

Analiza el contenido de **un archivo** del workspace autorizado.

- El archivo se lee completo solo hasta `JUDGMAN_MAX_FILE_BYTES` y se trata como
  dato no confiable: nunca se siguen instrucciones que aparezcan dentro.
- Usa `/file <ruta>`; la ruta debe estar dentro del workspace y se autocompleta.

## Cambiar de modo

Desde el chat:

```
/mode diagnose
/mode security
/mode file
```

También existen los atajos directos `/diagnose <pregunta>` y
`/security <texto>`, que cambian al modo correspondiente y lanzan la consulta en
un solo paso.

## Relación con los comandos de diagnóstico

Los comandos de evidencia (`/ports`, `/procs`, `/connections`, `/services`,
`/startup`, `/firewall`, `/hosts`, `/diagnostics`) funcionan en cualquier modo:
muestran los datos directamente en la consola, sin pasar por el modelo. Son la
forma más rápida de mirar evidencia cruda. Ver
[Diagnóstico](diagnostico.md).
