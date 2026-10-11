# Instalacion y primer arranque

## Instalar con pipx o uv

La instalacion se hace directo desde el repositorio de GitHub, sin publicar en
PyPI. La forma mas rapida es instalarlo como herramienta aislada, sin tocar el
Python del sistema:

```powershell
pipx install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

```bash
uv tool install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Tambien puedes instalarlo con `pip` dentro de un entorno virtual:

```powershell
python -m pip install "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Para fijar una version concreta, agrega el tag: `...judgman-mike.git@v0.1.0`.
En todos los casos queda disponible el comando `jmike`.

## Primer arranque

Ejecuta el chat:

```powershell
jmike
```

Si no hay configuracion, se lanza un asistente que pide la API key, el modelo y
la carpeta a vigilar. Los valores se guardan en el archivo de configuracion del
usuario:

- Windows: `%APPDATA%\judgman\config.env`
- macOS/Linux: `~/.config/judgman/config.env` (o `$XDG_CONFIG_HOME/judgman/config.env`)

En Unix el archivo se crea con permisos `600`. La clave nunca se guarda en el
proyecto.

## Reconfigurar y comprobar

- `jmike config` vuelve a lanzar el asistente.
- Dentro del chat, `/settings` reconfigura sin salir y `/snapshot` muestra los
  datos del sistema que se enviarian.

## Precedencia de la configuracion

De mayor a menor prioridad:

1. Opciones de la linea de comandos (`--model`, `--workspace`).
2. Variables de entorno (`JUDGMAN_*`).
3. Archivo `.env` en la carpeta actual.
4. Archivo de configuracion del usuario.
5. Valores por defecto.

## Desarrollar

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

## Versionar y publicar releases

El proyecto se distribuye con el repositorio (no por PyPI). Para marcar una
version, crea un tag y un release en GitHub:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Cualquiera puede instalar esa version con
`pipx install "git+https://github.com/MikeCardona076/Judgeman-mike.git@v0.1.0"`.
La integracion continua (`.github/workflows/ci.yml`) ejecuta las pruebas en
Windows, macOS y Linux en cada push y pull request.
