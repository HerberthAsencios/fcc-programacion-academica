# FCC-UNMSM · Contexto de trabajo para Codex

## Objetivo actual

Completar la **F4.1 · Construcción del Módulo 1**, dedicado a la recopilación de disponibilidad docente. El backend del flujo principal funciona en entorno local con datos de prueba. La F4.1 sigue en avance hasta completar los pendientes de interfaz y verificar el flujo integrado del docente y del responsable académico.

El **Módulo 2 · Programación académica** queda en pausa. Conserva su implementación y sus datos.

## Antes de editar

1. Abre la raíz real de `fcc-programacion-academica`. En la instalación local de Windows está en `C:\Users\TECNOLOGIA EDUCATIVA\Desktop\fcc-programacion-academica`.
2. Lee las instrucciones del repositorio. Revisa `git status --short` y `git diff` para distinguir el código base de los cambios que el usuario ya tiene en curso. Conserva también los archivos sin seguimiento.
3. Reproduce el primer pendiente del Módulo 1. Aplica un cambio pequeño y verificable, reutilizando los componentes, rutas y validaciones existentes.
4. Usa el código del repositorio como fuente de verdad. Si difiere de este documento, registra la diferencia antes de decidir qué cambiar.

## Límites del cambio

- Mantén fuera del alcance `backend/programacion/`, `worker_programacion` y las funciones de generación, ajustes e historial de propuestas.
- `frontend/src/App.jsx` y `backend/config/urls.py` son archivos compartidos. Si hay que editarlos, limita el diff a las secciones del Módulo 1. Conserva las rutas y los bloques de programación, incluido el que está dentro de `SeguimientoGestion`.
- Conserva los contratos de API existentes, los permisos por rol, las protecciones de sesión y CSRF, el historial de fichas y la auditoría.
- Usa una recopilación de prueba abierta y dedicada. Conserva los periodos, fichas, propuestas y volúmenes existentes. Evita reiniciar la base de datos, revertir cambios ajenos o incluir credenciales en el código.
- Evita cambios de esquema, dependencias o configuración salvo que sean necesarios para una brecha concreta del Módulo 1.

## Mapa del proyecto

| Punto de entrada | Qué contiene |
| --- | --- |
| `backend/disponibilidad/` | Modelos y vistas de disponibilidad docente, fichas y seguimiento. |
| `backend/config/urls.py` | Rutas compartidas. El docente usa `/api/disponibilidad/` y el responsable usa `/api/gestion/recopilaciones/`. |
| `frontend/src/App.jsx` | `Ficha`, `CursosBorrador`, `OpcionesCurso`, `CargaNoLectiva` y `SeguimientoGestion`. Reutiliza `solicitar` y `enviarJson` para las llamadas existentes. |
| Docker Compose | `backend` ejecuta Django con Python 3.12, `db` usa PostgreSQL y `frontend` ejecuta React con Vite. La aplicación abre en `http://127.0.0.1:5173/`. Django y su administrador están en `http://127.0.0.1:8000/`. |

## Estado conocido

- **Docente.** La interfaz contiene datos generales, cursos, opciones semanales, carga no lectiva, envío y consulta de la ficha recibida. Se verificaron por separado el borrador, las opciones, el envío y la conservación de revisiones.
- **Responsable académico.** Existen el seguimiento de fichas recibidas y pendientes, el cierre y la reapertura con auditoría, y la exportación CSV.
- **Pendiente inmediato.** Repetir el flujo completo desde una ficha vacía. Contrastar los campos y las reglas de envío con el Documento de Análisis vigente antes de añadir validaciones, en particular si dependen del tipo de dedicación docente.
- **Módulo 2 en pausa.** Ya existen la generación de propuestas, el cambio de salón y el historial de versiones. El servicio de cambio de opción semanal carga, pero su prueba funcional quedó pendiente por falta de una segunda opción habilitada con franjas completas en los datos existentes.

## Primera tarea y criterios de cierre

1. Inspecciona `Ficha`, sus rutas y las pruebas existentes. Usa las cuentas demo `demo_disponibilidad` y `demo_responsable` en sesiones separadas. Confirma que el docente esté convocado y que la recopilación esté abierta.
2. Como docente, completa los datos generales, agrega un curso y una opción semanal, guarda el borrador y recarga. Comprueba que se recuperen los datos y los bloques horarios.
3. Intenta enviar una ficha incompleta. La interfaz debe indicar qué falta y permitir corregirlo. Completa la ficha, envíala y comprueba que **Ficha recibida** siga accesible al recargar.
4. Como responsable, verifica que esa ficha figure como recibida. Comprueba el cierre, el bloqueo de edición para el docente, la reapertura autorizada con auditoría y la exportación CSV.
5. Corrige solo las brechas observadas. Al terminar, indica qué archivos cambiaste, qué pruebas pasaron y qué comprobaciones quedaron pendientes.

## Comprobaciones iniciales

```powershell
git status --short
git diff --stat
docker compose ps
docker compose exec backend python manage.py check
```

Revisa las pruebas existentes del Módulo 1 y los scripts de `frontend/package.json` antes de ejecutar las comprobaciones correspondientes. Si Docker o el entorno impiden ejecutar una prueba, identifica cuál quedó pendiente.

## Primer mensaje para Codex

> Lee `CONTEXTO_CODEX_MODULO_1.md` y las instrucciones del repositorio. Retoma la F4.1. Revisa los cambios locales, reproduce el primer pendiente del flujo del docente y aplica el cambio mínimo necesario. Preserva el avance del Módulo 2. Al terminar, resume los archivos modificados y las pruebas realizadas.

[Documentación oficial de Codex sobre AGENTS.md](https://developers.openai.com/codex/guides/agents-md)