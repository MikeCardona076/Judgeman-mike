# Judgman Mike

Judgman Mike es un agente pasivo de monitoreo del sistema de archivos para
desarrolladores y estudiantes. Vigila recursivamente una carpeta autorizada,
analiza automaticamente los archivos de texto creados o modificados y presenta
reportes pedagogicos en la interfaz local. Se instala como el comando `jmike` y
ofrece dos modos: un **chat interactivo en la terminal** (por defecto) y el
**monitor** con interfaz web.

## Instalar en un comando

La instalacion se hace directo desde el repositorio de GitHub, sin publicar en
PyPI. Con [pipx](https://pipx.pypa.io) o [uv](https://docs.astral.sh/uv/) no
necesitas crear un entorno virtual ni editar archivos a mano:

```powershell
pipx install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

```bash
uv tool install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Con `pip` dentro de un entorno virtual seria:

```powershell
python -m pip install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Para fijar una version concreta, agrega `@v0.1.0`, por ejemplo
`git+https://github.com/MikeCardona076/Judgeman-mike.git@v0.1.0`.

Luego ejecuta `jmike`. La primera vez, si no hay configuracion, se abre un
asistente que pide tu API key, el modelo y la carpeta a vigilar, y los guarda en
tu configuracion de usuario (`%APPDATA%\judgman\config.env` en Windows,
`~/.config/judgman/config.env` en macOS/Linux). Desde ahi todo se hace con
`jmike`.

## Primer arranque y configuracion

- `jmike` (o `jmike chat`) abre el chat. Si falta la API key, lanza el asistente.
- `jmike config` vuelve a lanzar el asistente en cualquier momento.
- Dentro del chat, `/settings` reconfigura sin salir y `/serve` inicia el monitor
  web en segundo plano.

Orden de precedencia de la configuracion (de mayor a menor):

1. Opciones de la linea de comandos (`--model`, `--workspace`).
2. Variables de entorno.
3. Archivo `.env` en la carpeta actual.
4. Archivo de configuracion del usuario.
5. Valores por defecto.

## Filosofia y seguridad

- El scanner solo escucha eventos `created` y `modified`. Puede leer archivos
  de texto para analizarlos, pero nunca escribe, renombra ni elimina archivos.
- El contenido de texto permitido se envia automaticamente al proveedor
  configurado con LiteLLM. No selecciones una carpeta que contenga material
  privado que no quieras enviar a ese proveedor.
- Archivos binarios, archivos mayores que `JUDGMAN_MAX_FILE_BYTES` y nombres o
  directorios habituales de credenciales se excluyen del analisis.
- Las rutas del workspace se resuelven y validan, incluidos los enlaces
  simbolicos, antes de leer los archivos observados.
- El servidor escucha unicamente en `127.0.0.1`; la API no habilita CORS.
- La explicacion del modelo es material educativo, no una auditoria de seguridad
  ni una instruccion para ejecutar codigo.

## Requisitos previos

- Python 3.11 o posterior. Verifica con `py --version` (Windows) o
  `python3 --version` (macOS/Linux).
- Una clave de API para un proveedor compatible con LiteLLM.
- Windows, macOS o Linux.

## Ejecucion paso a paso

Los pasos usan Windows con PowerShell; las notas indican la variante para
macOS/Linux.

1. **Abre una terminal en la carpeta del proyecto.** Debes ver `pyproject.toml`,
   `requirements.txt` y la carpeta `judgman`.

2. **Crea el entorno virtual.**

   ```powershell
   py -m venv .venv
   ```

   macOS/Linux:

   ```bash
   python3 -m venv .venv
   ```

3. **Activa el entorno virtual.**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

   macOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

   Si PowerShell bloquea el script de activacion, ejecuta una vez
   `Set-ExecutionPolicy -Scope Process Bypass` y repite el comando.

4. **Instala el paquete y sus dependencias** (habilita el comando `jmike`).

   ```powershell
   python -m pip install -e ".[dev]"
   ```

   `python -m pip install -r requirements.txt` hace lo mismo.

5. **Crea el archivo `.env` a partir de la plantilla.**

   ```powershell
   Copy-Item .env.example .env
   ```

   macOS/Linux:

   ```bash
   cp .env.example .env
   ```

6. **Edita `.env` con tus valores.** El archivo `.env` esta excluido de Git.

   | Variable | Descripcion | Valor por defecto |
   |----------|-------------|-------------------|
   | `JUDGMAN_API_KEY` | Clave del proveedor (obligatoria). | - |
   | `JUDGMAN_MODEL` | Identificador de modelo aceptado por LiteLLM. | `openai/gpt-4o-mini` |
   | `JUDGMAN_WORKSPACE` | Directorio autorizado a vigilar. | `.` |
   | `JUDGMAN_MAX_FILE_BYTES` | Tamano maximo leido para analisis. | `131072` |
   | `JUDGMAN_PORT` | Puerto de la API local. | `8765` |
   | `JUDGMAN_ENABLE_SYSTEM_INFO` | Habilita preguntas sobre el sistema. | `true` |
   | `JUDGMAN_MAX_QUESTION_CHARS` | Limite de la pregunta al sistema. | `2000` |
   | `JUDGMAN_PATH_TOOLS_LIMIT` | Maximo de ejecutables del PATH incluidos. | `40` |

   Reemplaza `JUDGMAN_API_KEY` por tu clave real y ajusta `JUDGMAN_WORKSPACE`
   con la ruta del directorio que quieres vigilar (una ruta absoluta es mas
   segura que `.`).

7. **Abre el chat en la terminal.**

   ```powershell
   jmike
   ```

   Escribe tu pregunta y pulsa Enter. Consulta la seccion **Chat en terminal**
   para los comandos disponibles.

8. **O inicia el monitor con interfaz web.**

   ```powershell
   jmike serve
   ```

   La API local queda en `http://127.0.0.1:8765`, se abre la interfaz en el
   navegador y aparece un icono en la bandeja del sistema. Cada archivo de texto
   nuevo o modificado bajo el directorio autorizado se analiza automaticamente y
   la interfaz muestra el estado y el reporte.

9. **Usa la interfaz web.** Revisa "Cambios recientes" para ver los analisis
   automaticos, pega un fragmento en "Analisis manual" para una consulta extra,
   o usa "Preguntas sobre el sistema operativo" para dudas sobre tu maquina
   (revisa antes el desplegable con los datos que se enviaran).

10. **Deten la aplicacion.** En el chat, escribe `/exit` o pulsa `Ctrl+D`. En el
    monitor, usa la opcion **Salir** del icono en la bandeja o `Ctrl+C` en la
    terminal. Si el proveedor rechaza la solicitud, el error se registra en la
    consola.

## Chat en terminal (jmike)

El comando `jmike` abre un chat interactivo (estilo opencode) en la consola.

```powershell
jmike            # chat interactivo (por defecto)
jmike chat       # igual que jmike
jmike serve      # monitor con API local, web y bandeja
jmike config     # asistente de configuracion
jmike ask "como veo los procesos activos en Windows?"
jmike analyze .\notas.txt
```

Opciones globales: `--model` y `--workspace` sobrescriben `JUDGMAN_MODEL` y
`JUDGMAN_WORKSPACE` solo para esa ejecucion.

Comandos dentro del chat:

| Comando | Descripcion |
|---------|-------------|
| `/help` | Muestra la ayuda. |
| `/system` | Modo preguntas sobre el sistema operativo. |
| `/code` | Modo preguntas de codigo o generales. |
| `/file <ruta>` | Analiza un archivo dentro del workspace. |
| `/snapshot` | Muestra los datos del sistema que se enviarian. |
| `/serve` | Inicia el monitor web en segundo plano. |
| `/settings` | Reconfigura la API key, el modelo o el workspace. |
| `/clear` | Borra el historial de la conversacion. |
| `/exit` , `/quit` | Sale del chat. |

Las respuestas se muestran en streaming. Cada consulta se envia al proveedor
configurado, igual que el resto de funciones.

## Preguntas sobre el sistema

El panel **Preguntas sobre el sistema operativo** (paso 9) permite consultar
dudas sobre tu maquina. Para responder, Judgman recolecta un conjunto de datos
benignos de solo lectura (version y arquitectura del SO, version de Python,
numero de CPUs, memoria, uso de disco del workspace, zona horaria, nombres de
variables de entorno y nombres de ejecutables del PATH) y los envia al proveedor
configurado como contexto. Los datos recolectados se muestran en la propia
interfaz antes de preguntar.

- Nunca se ejecutan comandos del sistema: solo se usan APIs de Python.
- Solo se envian **nombres** de variables de entorno, nunca sus valores.
- No se incluyen usuario, hostname, seriales, direcciones IP ni rutas absolutas.
- Ajusta el comportamiento con `JUDGMAN_ENABLE_SYSTEM_INFO` (por defecto `true`),
  `JUDGMAN_MAX_QUESTION_CHARS` (2000) y `JUDGMAN_PATH_TOOLS_LIMIT` (40).

## Pruebas

Ejecuta las pruebas desde la raiz del proyecto con el entorno virtual activado:

```powershell
python -m pytest
```

Las pruebas cubren el confinamiento de rutas, enlaces simbolicos, el
comportamiento de lectura exclusiva del scanner, la recoleccion de datos del
sistema, los endpoints de la API, la sesion de chat y la CLI.

## Solucion de problemas

1. **`jmike` no se reconoce como comando.** Instala el paquete en modo editable
   con `python -m pip install -e ".[dev]"` y reabre la terminal.
2. **Error porque falta `JUDGMAN_API_KEY` o sigue en `replace-with-your-provider-api-key`.**
   Ejecuta `jmike config` para el asistente, o copia `.env.example` a `.env` y
   coloca una clave real.
3. **`JUDGMAN_WORKSPACE debe ser un directorio existente`.** Apunta la variable a
   una carpeta que exista; usa una ruta absoluta para evitar ambiguedades.
4. **`Activate.ps1` bloqueado por politicas de ejecucion.** Ejecuta
   `Set-ExecutionPolicy -Scope Process Bypass` en la sesion actual y repite la
   activacion.
5. **El proveedor rechaza la solicitud.** Revisa `JUDGMAN_MODEL` y
   `JUDGMAN_API_KEY`; el detalle del error queda en la consola.
6. **No aparece el icono de bandeja.** La aplicacion sigue funcionando en el
   navegador en `http://127.0.0.1:8765`; revisa la consola por si el entorno no
   soporta `pystray`.
7. **El puerto ya esta en uso.** Cierra la otra instancia o cambia `JUDGMAN_PORT`
   en `.env`.
