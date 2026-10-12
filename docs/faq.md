# Preguntas frecuentes

## ¿Qué es exactamente JudgeMan-Mike?

Un agente local de **diagnóstico y seguridad**. Le cuentas qué falla (un puerto,
un proceso, un servicio, un archivo sospechoso); reúne evidencia de tu equipo en
modo solo lectura, la interpreta y, cuando hace falta cambiar algo, **propone** la
acción exacta y solo la ejecuta si la apruebas.

## ¿Modifica mi sistema sin permiso?

No. El diagnóstico es de solo lectura y ninguna reparación se ejecuta sin una
confirmación `y/N`. Además, todas las acciones quedan en un log de auditoría.

## ¿Puede ejecutar cualquier comando que le pida el modelo?

No. El modelo solo puede proponer acciones de un catálogo cerrado
([Acciones](acciones.md)). Los comandos se construyen en código y se ejecutan sin
*shell*, así que no hay forma de inyectar comandos.

## ¿A dónde van mis datos?

Al proveedor LLM que configures. Antes de enviar, JudgeMan-Mike redacta la carpeta
personal y el usuario, y acota el texto. Nada sale por otro sitio: la única salida
de red es la llamada al modelo. Usa `/diagnostics` para ver qué se enviaría.

## ¿Funciona sin `psutil`?

Sí, con limitaciones. Sin el extra `monitor`, los puertos, procesos y conexiones
no están disponibles y los gauges del HUD degradan a valores aproximados.

```powershell
pipx install "judgman-mike[monitor] @ git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

## ¿Necesito permisos de administrador?

Para leer el diagnóstico, no. Para aplicar algunas reparaciones (firewall,
servicios) puede que sí; si el sistema rechaza por permisos, aparece en el
resultado y en la auditoría. Vuelve a intentarlo desde una terminal elevada.

## ¿Por qué "no escucha nada en ese puerto" y no "lo bloqueó el firewall"?

Porque un firewall no puede bloquear un puerto donde **nada** está escuchando. Si
nada escucha, el problema es que el servicio no corre o usa otro puerto. Esa
distinción es parte del diagnóstico honesto de JudgeMan-Mike.

## ¿Hay versión de pago?

El core es MIT y es gratis. Hay un Pro en preparación (monitor continuo con
alertas, historial, auditoría firmada, catálogo ampliado y más). Ver el
[Roadmap](roadmap.md). En esta versión, `/pro` describe lo que está por llegar y
lo marca como "no disponible".

## ¿Cómo actualizo?

JudgeMan-Mike te avisa cuando hay una versión nueva. Desde el chat usa `/update`
(comprueba) o `/update --run` (actualiza tras confirmar); desde la terminal,
`jmike update` o `jmike update --check`. También puedes reinstalar a mano:

```powershell
pipx install --force "git+https://github.com/MikeCardona076/Judgeman-mike.git"
```

Ver [Actualizaciones](actualizaciones.md).

## ¿Se actualiza sola?

Solo si lo activas con `JUDGMAN_AUTO_UPDATE=true`. Por defecto **avisa y pide
confirmación**: nada se ejecuta sin tu `y`. La comprobación se puede desactivar
con `JUDGMAN_CHECK_UPDATES=false`.

## La consola ocupa toda la pantalla, ¿puedo evitarlo?

Sí: ejecuta `jmike --plain` para usar la consola simple en línea.
