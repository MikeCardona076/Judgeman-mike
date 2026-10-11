# Como interpretar las advertencias de Judgman

Judgman vigila en modo pasivo los archivos de la carpeta de trabajo seleccionada.
No certifica que el sistema o un programa sean seguros: el analizador puede
equivocarse, omitir contexto o describir un riesgo hipotetico.

La misma analitica esta disponible por linea de comandos con `jmike` (chat
interactivo), `jmike ask "pregunta"` y `jmike analyze <ruta>`. Estas ordenes
envian al proveedor el mismo tipo de contenido que la interfaz web.

## Recorrido seguro de una ruta

Una ruta relativa como `src/app.py` se resuelve dentro del workspace. Una ruta
como `..\..\Windows\win.ini`, o un enlace simbolico que apunte fuera del
workspace, se rechaza. Esta comprobacion limita los archivos que el scanner
puede leer; no cambia permisos del sistema operativo ni modifica el contenido.

## Fragmentos de codigo y logs

El scanner lee archivos de texto dentro de la carpeta autorizada y envia su
contenido al proveedor indicado por `JUDGMAN_MODEL` y `JUDGMAN_API_KEY` para
analizarlos automaticamente. Los archivos binarios, grandes y las rutas o
nombres habituales de credenciales se excluyen. Estas exclusiones no detectan
todos los secretos: elige una carpeta que no contenga informacion privada que
no quieras transmitir. Tambien puedes pegar manualmente un fragmento en la
interfaz para solicitar un analisis adicional.

Antes de seleccionar la carpeta, quita claves, tokens, cookies, datos
personales, direcciones internas y cualquier informacion que no quieras enviar
a un servicio externo. No ejecutes los ejemplos sugeridos sin revisarlos y
probarlos en un entorno aislado.

## Preguntas sobre el sistema operativo

El panel de preguntas del sistema envia al proveedor un snapshot de solo lectura
con datos no sensibles de la maquina: version y arquitectura del SO, version de
Python, numero de CPUs, memoria, uso de disco del workspace, zona horaria,
nombres de variables de entorno y nombres de ejecutables del PATH. Nunca se
ejecutan comandos, nunca se envian valores de variables de entorno y nunca se
incluyen usuario, hostname, seriales, direcciones IP ni rutas absolutas. Puedes
revisar el snapshot en la interfaz y desactivar la funcion con
`JUDGMAN_ENABLE_SYSTEM_INFO=false`.
