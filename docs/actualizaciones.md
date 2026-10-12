# Actualizaciones

JudgeMan-Mike se instala desde GitHub y puede avisarte cuando hay una versión
nueva y actualizarse por ti. **Nunca cambia nada sin tu confirmación** (salvo que
lo actives explícitamente).

## Cómo sabe cuál es la última versión

Como el paquete no se publica en PyPI, la "última versión" se lee del propio
repositorio: se descarga `judgman/__init__.py` de la rama `main` y se compara su
`__version__` con la tuya. No se envía ningún dato; es una petición HTTP de solo
lectura.

- La comprobación tiene un *timeout* corto y es **silenciosa** si no hay red.
- El resultado se **cachea 24 h** en `%APPDATA%\judgman\update-check.json`
  (o `~/.config/judgman/update-check.json`), así que no consulta en cada arranque.

## Aviso al arrancar

Al iniciar el chat, JudgeMan-Mike mira la caché (sin red) y, si hay una versión
nueva, muestra:

```
Nueva version 0.2.0 disponible (tienes 0.1.0). Usa /update para actualizar.
```

En segundo plano refresca la caché para el próximo arranque. Puedes desactivar
todo con `JUDGMAN_CHECK_UPDATES=false`.

## Actualizar desde el chat

```
/update          # comprueba y muestra si hay una versión nueva
/update --run    # comprueba y, tras confirmar con y/N, actualiza
```

`/update --run` reinstala el paquete y, al terminar, te pide **reiniciar `jmike`**
para usar la nueva versión.

## Actualizar desde la terminal

```powershell
jmike update           # comprueba y actualiza (con confirmacion y/N)
jmike update --check   # solo comprueba; no actualiza
```

## Qué comando de instalación se usa

Se detecta automáticamente cómo está instalado el paquete:

- **pipx** (si detecta `PIPX_HOME` o una ruta de pipx) →
  `pipx install --force <git-url>`.
- **pip** (por defecto) →
  `python -m pip install --upgrade --force-reinstall <git-url>`.

Ambos se ejecutan **sin shell**. Si prefieres hacerlo a mano, el comando exacto
se muestra en el panel de `/update`.

## Configuración

| Variable | Por defecto | Descripción |
|----------|-------------|-------------|
| `JUDGMAN_CHECK_UPDATES` | `true` | Comprueba al arrancar (cacheada 24 h). |
| `JUDGMAN_AUTO_UPDATE` | `false` | Reinstala sola si hay versión nueva (opt-in). |

## Nota de seguridad

Actualizar implica ejecutar código nuevo descargado del repositorio remoto. Por
eso el flujo por defecto es **avisar y confirmar**. Activa `JUDGMAN_AUTO_UPDATE`
solo si confías en el origen y quieres el modo desatendido.
