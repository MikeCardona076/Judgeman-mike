# Seguridad y privacidad

JudgeMan-Mike está diseñado para un principio: **mirar mucho, cambiar poco y
dejar rastro**. Esta página resume las garantías y sus límites.

## Solo lectura por defecto

- El diagnóstico (puertos, procesos, conexiones, servicios, arranque, firewall,
  `hosts`) usa `psutil`, lecturas de archivos y comandos de **consulta**
  ejecutados sin *shell*. Nada se modifica sin tu aprobación.
- El monitor web escucha eventos `created` y `modified` de archivos y **nunca**
  escribe, renombra ni elimina.

## Reparación con confirmación

- El modelo **no ejecuta comandos libres**. Solo puede proponer acciones de un
  catálogo cerrado ([Acciones](acciones.md)).
- El comando se construye como una lista de argumentos y se ejecuta con
  `shell=False`: no hay interpolación de texto en una línea de shell, así que no
  hay metacaracteres que permitan inyección.
- Cada acción se muestra con su comando y su riesgo y exige confirmación
  explícita (`y/N`).

## Auditoría

Toda acción propuesta, confirmada, rechazada o fallida se registra en JSON, una
línea por evento:

- Windows: `%APPDATA%\judgman\audit.log`
- macOS/Linux: `~/.config/judgman/audit.log`

## Privacidad de los datos enviados

- El diagnóstico puede contener rutas, usuarios o IPs. Antes de enviarlo al
  proveedor se **redactan** la carpeta personal (`~`) y el nombre de usuario
  (`<usuario>`), y las credenciales de un proxy (`<credenciales>`).
- El texto se acota a un tamaño máximo.
- Usa `/diagnostics` para ver exactamente lo que se enviaría, antes de preguntar.
- En las preguntas sobre el sistema operativo (monitor web) **solo se envían
  nombres** de variables de entorno, nunca sus valores; no se incluyen usuario,
  hostname, seriales, direcciones IP ni rutas absolutas.

## Aislamiento de red

- El servidor del monitor escucha únicamente en `127.0.0.1`.
- La API no habilita CORS.
- La única salida a la red es la llamada al proveedor LLM configurado
  (`judgman/core/analyzer.py`).

## El contenido es dato no confiable

- El texto de archivos o pegado por el usuario se trata como **datos**, nunca
  como instrucciones. JudgeMan-Mike no sigue órdenes encontradas dentro de un
  archivo o de la salida de un comando.

## Límites honestos

- JudgeMan-Mike **no certifica** que un sistema o un programa sean seguros. El
  modelo puede equivocarse, omitir contexto o describir un riesgo hipotético.
- Algunas lecturas (PID de ciertos puertos, servicios) pueden requerir permisos
  elevados; cuando no hay acceso, se indica con una nota en vez de inventar datos.
- Si configuras la carpeta a vigilar con datos privados, esos datos pueden
  enviarse al proveedor. Elige la carpeta y el proveedor con criterio.

Para reportar una vulnerabilidad, consulta [SECURITY.md](../SECURITY.md).
