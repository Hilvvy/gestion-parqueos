# Gestión de parqueos ULACIT

Monolito Django para reservar espacios dentro del horario de clases, registrar ingresos y salidas y consultar la ocupación de tres parqueos. Integra vehículos, perfiles ampliados, materias semanales, confirmaciones con QR local, recomendación de parqueo, alertas de seguridad, cuenta regresiva, indicadores mensuales, administración propia, reportes y auditoría. La interfaz mantiene un diseño Material/Metro sencillo con acento morado.

## Requisitos y ejecución

Python 3.12, Git y un navegador. La base local es SQLite; no requiere SQL Server ni Docker en esta etapa.

```powershell
git clone https://github.com/Hilvvy/gestion-parqueos.git
cd gestion-parqueos
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo
.\start.ps1
```

Abre http://127.0.0.1:8000. `start.ps1` inicia el servidor web y el procesador de ausencias; al terminar el servidor detiene ese procesador. Si ya existe un servidor en 8000, ciérralo antes de iniciar otro.

También puedes usar dos terminales dentro del proyecto:

```powershell
# Terminal 1
.\.venv\Scripts\python manage.py runserver

# Terminal 2: necesario para vencer citas aunque nadie abra el sitio
.\.venv\Scripts\python manage.py process_no_shows --watch
```

`process_no_shows` sin `--watch` ejecuta una sola pasada, útil también desde un programador de tareas. El procesador revisa cada 15 segundos. La entrada valida el plazo en el servidor, incluso cuando el procesador está detenido.

## Cuentas y datos de demostración

`seed_demo` solicita una contraseña para las cuentas nuevas y nunca cambia las contraseñas existentes. No borra reservas ni vehículos previos. Configura estas cuentas:

| Usuario | Acceso |
| --- | --- |
| estudiante | Vehículo DEMO123, perfil, siete días de horarios ficticios de 07:00 a 22:00 y reservas propias |
| oficial | Grupo Seguridad y asignación a los tres parqueos demo |
| administrador | Administración de usuarios/parqueos/reglamento dentro de la app, reportes, indicadores y auditoría |

La cuenta `administrador` se crea como superusuario solo si no existía. El comando agrega los grupos correspondientes a las cuentas demo existentes. Está destinado al entorno académico local, no al aprovisionamiento de usuarios de una institución.

Repite `seed_demo` para cargar nuevos días cuando los horarios demo caduquen. También puedes registrar materias semanales en **Materias**, o hacerlo para otro usuario desde **Administración → Usuarios → Materias**. Se generan de 1 a 16 semanas de clases, conservando fecha y hora precisas para validar las reservas. Los horarios registrados por el propio estudiante se muestran como **Autodeclarados**; son datos del prototipo, no una integración ni verificación institucional.

El acceso acepta usuario o correo. Los correos iniciales demo son `estudiante@parqueos.example`, `oficial@parqueos.example` y `administrador@parqueos.example` cuando la cuenta no tenía correo. No se envían mensajes. Si existe un correo duplicado en datos anteriores, el acceso por ese correo se rechaza; el usuario sigue pudiendo entrar con su nombre. Las pantallas propias evitan nuevos correos duplicados.

Administración permite crear/editar usuarios, definir rol, cédula, nacimiento, carrera, jornada/horario del oficial y parqueos asignados, y activar/desactivar cuentas conservando el historial. Una cuenta desactivada pierde acceso a sus sesiones. Las contraseñas iniciales se validan con Django; editar datos no cambia la contraseña. Nadie puede desactivar su propia cuenta. Los administradores ordinarios no pueden modificar superusuarios. Para crear un superusuario adicional sigue disponible `python manage.py createsuperuser`.

## Recorrido de demostración

1. Entrar como estudiante y revisar Vehículos; registrar o retirar uno sin perder su historial.
2. Registrar una materia semanal si hace falta, reservar con un vehículo propio dentro de una de sus clases y dejar Parqueo en **Asignación recomendada**. Consultar el código y QR de confirmación y la cuenta regresiva de la próxima visita.
3. Intentar otra reserva con la misma placa y franja para comprobar el rechazo, o cancelar antes del inicio.
4. Para demostrar ingreso, reservar desde el próximo minuto y esperar. Entrar como oficial en otro navegador, buscar la placa o pegar el código completo, registrar ingreso y luego salida.
5. Revisar la ocupación física: se actualiza cada cinco segundos sin recarga. Las reservas futuras no se cuentan como vehículos dentro.
6. Entrar como administrador a Reportes, filtrar por placa, fechas y estado y exportar exactamente ese conjunto a CSV. En **Indicadores** elegir el mes y consultar totales, cancelaciones, parqueo más solicitado, hora de mayor demanda y estados. Revisar Auditoría para ver los eventos y sus responsables.
7. En **Administración** crear/editar un usuario u oficial, asignarle parqueos y probar activar/desactivar. En Parqueos cambiar capacidad/estado; no se permiten cambios que dejen sin cupo las reservas comprometidas o los vehículos dentro. En Reglamento cambiar la tolerancia para las reservas nuevas.
8. En Control de acceso consultar las alertas de llegadas dentro de los próximos 30 minutos y las citas pendientes dentro de su tolerancia. Se actualizan cada cinco segundos y solo incluyen los parqueos autorizados.

El QR contiene el código opaco de la reserva y se genera localmente con Segno, sin enviar datos a servicios externos. Puede leerse con un lector QR y pegarse en la consola. No incluye un lector de cámara dentro del navegador. Código o QR por sí solos no permiten operar: la consola requiere autenticación y asignación al parqueo.

## Reglas acordadas para este incremento

- Tres parqueos iniciales. Administración permite crear, editar o desactivar parqueos; las reservas y la disponibilidad solo usan los activos. No se elimina el historial.
- Reservas futuras contenidas en uno de los horarios activos del usuario. Se puede indicar curso, trámite/cita o evento como motivo; todos conservan esa validación. No se imponen las ventanas de 12–72 horas ni las duraciones fijas de la demo de referencia.
- Solo se permite reservar con un vehículo activo propio. Las placas se normalizan y no puede haber dos vehículos activos con la misma placa.
- Se puede retirar un vehículo y registrar un reemplazo, incluso del mismo tipo. No se impone un máximo por tipo. Se impide el retiro cuando tiene reservas pendientes o permanece dentro.
- Se puede cancelar antes del inicio, sin exigir una hora de anticipación.
- La tolerancia de llegada es configurable en **Administración → Reglamento**; su valor inicial demo es 15 minutos. Cada reserva conserva el plazo establecido al crearla. Cambiar la política afecta las reservas nuevas.
- Una cita sin ingreso pasa a Vencida al superar ese plazo o alcanzar su hora final. Su QR deja de emitirse y el código ya no permite ingreso. La inasistencia queda en auditoría y puede filtrarse en reportes.
- Un ingreso anticipado, vencido, duplicado, de otro parqueo o con cupo físico agotado se rechaza. Un vehículo que excede su hora prevista sigue ocupando espacio hasta registrar su salida.
- El grupo Seguridad opera sus parqueos asignados. Administración con permiso `parking.manage_operations` y los superusuarios pueden operar todos los parqueos activos. `is_staff` por sí solo no concede ese acceso.
- Reportes requiere `parking.view_operational_report`; Auditoría requiere `parking.view_auditevent`. El grupo Administración recibe ambos permisos y `parking.manage_operations` para las pantallas propias. Seguridad no puede concederse ese permiso ni cambiar roles.

## Calidad

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
```

La suite actual incluye **116 pruebas**. GitHub Actions ejecuta los mismos controles en push y pull request. Las pruebas usan bases aisladas de los datos demo. Se incluyen reglas de horarios y capacidad, propiedad de vehículos, permisos, QR privado y cancelado, tolerancia y ausencia idempotente, historial/CSV, auditoría, migración de registros antiguos y dos solicitudes simultáneas por el último espacio, tanto con parqueo explícito como con asignación recomendada. También se prueban administración, perfiles ampliados, materias recurrentes, alertas, indicadores por mes local y el recorrido funcional completo.

La prueba concurrente usa dos conexiones sobre un archivo SQLite temporal en un proceso aislado: debe confirmar una sola solicitud y rechazar la otra por capacidad. Se usa `BEGIN IMMEDIATE` en transacciones breves para evitar la carrera entre consultar el cupo y asignarlo. No equivale a una prueba de carga o a validar otro motor de base de datos.

## Organización

- `config/`: configuración y rutas del monolito.
- `parking/models.py`: entidades y restricciones de integridad.
- `parking/services.py`: reglas y transiciones de reservas y vehículos, con auditoría en la misma transacción.
- `parking/queries.py`: ocupación, recomendación, alertas, historial e indicadores.
- `parking/capacity.py`: cálculo compartido del máximo simultáneo por intervalos.
- `parking/administration.py`: servicios de perfiles, usuarios, parqueos y materias.
- `parking/management_views.py` y `subject_views.py`: pantallas administrativas y académicas.
- `parking/authentication.py`: acceso por usuario o correo mediante el backend de Django.
- `parking/permissions.py`: roles y asignaciones de seguridad.
- `parking/forms.py` y `views.py`: validación de entradas y coordinación HTTP.
- `templates/` y `static/`: interfaz HTML/CSS/JavaScript adaptable.
- `parking/management/commands/`: semilla y procesador de ausencias.
- `parking/tests/`: pruebas unitarias, de integración, migración y concurrencia.

Se conserva una sola app de dominio con separación por responsabilidades. Las funciones de la demo `ParqueoU_Demo_v3/ParqueoU_Demo_v1` del equipo se usaron como referencia funcional para vehículos, perfiles, confirmación, reportes, auditoría y orientación de próxima reserva. La integración utiliza los modelos, servicios y mecanismos de seguridad de Django.

## Actualizar una instalación existente

Respalda `db.sqlite3`, instala las dependencias y ejecuta `migrate`. La migración conserva las reservas, asigna un UUID diferente a cada una y establece su plazo de llegada inicial. Las reservas antiguas conservan su placa como dato histórico; no se les inventa un propietario de vehículo. Las reservas nuevas sí requieren un vehículo registrado. No se fabrican eventos de auditoría para operaciones anteriores a esta integración.

Vuelve a ejecutar `seed_demo` en el entorno demo para agregar roles, asignaciones, cuenta administrativa y vehículo inicial. Los usuarios que solo tenían `is_staff` deben recibir grupo y parqueos explícitamente para operar la consola. Reinicia el servidor y el procesador. Después de actualizar el backend de acceso, vuelve a iniciar sesión.

## Paridad con la demo del equipo

[La matriz de paridad](docs/paridad-demo.md) enumera las funciones trasladadas y las reglas que se adaptaron al proyecto acordado. Incluye todos los flujos funcionales de la demo recibida; no convierte los pendientes originales del backlog en funcionalidades terminadas.

## Estado frente al backlog y límites

| Elemento | Incremento disponible | Pendiente |
| --- | --- | --- |
| TT-01 | Monolito, migraciones, README, CI y pruebas | Docker Compose, SQL Server y decisión de separación futura por apps |
| TT-02 | Organización y decisiones descritas en README | Diagramas y ADR formales |
| HU-01 | Horario de clases, vehículo sin traslapes, QR local y cancelación | Revisión de aceptación del equipo |
| HU-02 | Capacidad por intervalo y prueba concurrente del último cupo | Carga y validación al migrar de motor |
| HU-03 | — | Visitantes autorizados |
| HU-04 | Placa/código, permisos por parqueo, horario/tolerancia, cupo y auditoría de ingreso/salida | Acceso excepcional y medición del objetivo de 10 segundos |
| HU-05 | Ocupación física, actualización cada cinco segundos y hora de consulta | Medición de rendimiento institucional |
| HU-06 | Tolerancia configurable, procesador periódico, estado Vencida, QR inválido y auditoría | Revisión de aceptación y operación del procesador en despliegue |
| HU-07 | Historial por placa/fechas/estado, permisos, CSV y auditoría | Medición del objetivo de cinco segundos |
| HU-08 | — | Operación sin conexión y sincronización |

No incluye integración con horarios institucionales, hardware de acceso ni despliegue productivo. Los tiempos máximos de respuesta no se declaran medidos. Las reservas, los parqueos, las materias recurrentes, los vehículos y los eventos son de solo lectura en el admin de Django; las operaciones normales se realizan en las pantallas propias con sus servicios y auditoría.

Variables opcionales: `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `PARKING_DATABASE_PATH`. `.env.example` documenta las opciones, pero no se carga automáticamente. `runserver` y la clave predeterminada son para desarrollo local.

Referencias: [transacciones SQLite en Django 5.2](https://docs.djangoproject.com/en/5.2/ref/databases/#transactions-behavior) y [Segno](https://pypi.org/project/segno/).
