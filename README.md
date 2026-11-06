# Gestión de parqueos ULACIT

Prototipo académico para la retrospectiva del curso de aseguramiento de calidad. Un monolito Django con HTML, CSS y JavaScript; SQLite permite ejecutarlo sin instalar un servidor de base de datos.

## Ejecutar en Windows

Desde la carpeta del proyecto:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo
.\.venv\Scripts\python manage.py runserver
```

Abre http://127.0.0.1:8000. `seed_demo` solicita una contraseña para las cuentas **estudiante** y **oficial**. Crea tres parqueos y horarios ficticios de clases de 07:00 a 22:00 durante siete días, hora de Costa Rica. Los usuarios existentes conservan su contraseña. Puedes repetir el comando para cargar nuevos días.

Para administrar usuarios, capacidades y horarios: ejecuta `python manage.py createsuperuser` usando el entorno virtual y visita `/admin/`. Los usuarios activos con `is_staff` pueden operar la consola del oficial.

## Demostración de cinco minutos

1. Ingresar como estudiante y consultar los tres parqueos.
2. Reservar dentro del horario de clases desde el próximo minuto. Intentar otra reserva con la misma placa y horario para ver la validación.
3. Cancelar una reserva antes de su inicio y crear otra.
4. Esperar al inicio de la reserva. En otro navegador, ingresar como oficial, buscar la placa y registrar ingreso.
5. Revisar la ocupación en el panel del estudiante, que actualiza cada cinco segundos. Registrar salida desde la consola y comprobar la liberación del espacio.

## Calidad

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format --check .
.\.venv\Scripts\python manage.py check
.\.venv\Scripts\python manage.py makemigrations --check --dry-run
```

GitHub Actions ejecuta estos controles en cada push y pull request. El workflow está preparado; se ejecutará remotamente cuando el código se suba a GitHub. Las pruebas usan una base aislada de la demo y verifican reglas de negocio, permisos y flujos HTTP.

Validación local inicial: 31 pruebas aprobadas, Ruff y formato correctos, comprobaciones de Django sin errores y migraciones al día. El servidor respondió HTTP 200 para el acceso y los estilos. La revisión visual en navegador queda pendiente.

## Organización

- `config/`: configuración, rutas y WSGI.
- `parking/models.py`: entidades y restricciones de integridad.
- `parking/services.py`: clase con las reglas y transiciones de reservas.
- `parking/forms.py` y `views.py`: entrada de datos y coordinación HTTP.
- `templates/` y `static/`: interfaz adaptable sin dependencias frontend.
- `parking/tests/`: pruebas con pytest y pytest-django.

Una sola app de dominio es suficiente para este alcance. Los modelos encapsulan la persistencia y el servicio concentra las reglas, sin capas abstractas innecesarias. Django proporciona autenticación, sesiones, escape HTML y CSRF. Las modificaciones requieren POST. El estudiante solo consulta y cancela sus propias reservas; el oficial controla los movimientos. El administrador consulta las reservas en modo de solo lectura para evitar saltarse las reglas.

## Relación con el backlog

| Elemento | Funcionalidad disponible | Pendiente |
| --- | --- | --- |
| TT-01 | Repositorio local, entorno, README, pruebas y CI | Docker Compose, SQL Server y ejecución remota de Actions |
| HU-01 / RF-01 | Reserva dentro de clases, placa sin traslapes y cancelación | QR y modificación de citas |
| HU-02 / RF-02 | Capacidad por intervalo y reserva transaccional | Prueba concurrente, carga y asignación por tipo de usuario |
| HU-04 / RF-04 | Búsqueda por placa, ingreso/salida y registro de hora y oficial de ingreso | QR, tolerancia configurable y accesos excepcionales |
| HU-05 / RF-05 | Ocupación física, actualización cada 5 segundos y hora de consulta | Medición de rendimiento institucional |

Son partes funcionales de historias; no se declaran historias completas. No incluye visitantes, reportes avanzados, operación sin conexión, integración académica ni expiración automática (HU-06). Una reserva sin ingreso deja de afectar intervalos futuros al terminar su franja, pero no pasa automáticamente a Vencida. Un vehículo que permanece dentro ocupa espacio hasta registrar la salida.

SQLite usa una escritura inicial dentro de la transacción para serializar las reservas; ante contención se pide reintentar. Esto no equivale a validar concurrencia en producción. SQL Server requiere su propia configuración y pruebas en la siguiente iteración. Tampoco se ha medido todavía la meta de ingreso en menos de 10 segundos.

Configuración opcional mediante variables de entorno: `DJANGO_DEBUG`, `DJANGO_SECRET_KEY` y `DJANGO_ALLOWED_HOSTS`. `.env.example` documenta los nombres; el archivo no se carga automáticamente. `runserver` y la clave predeterminada se usan para desarrollo local.

## Para la retrospectiva

Logrado: recorrido visible reserva → ingreso → ocupación → salida, reglas centralizadas y controles automáticos. Temas para discutir: ajustar el documento a un monolito, acordar tolerancia y alcance mínimo, añadir prueba concurrente e incorporar SQL Server y Docker en otra iteración. Usar ramas `feature/` o `fix/` y revisión por otro integrante antes de integrar.

Referencia: [Pruebas en Django 5.2](https://docs.djangoproject.com/en/5.2/topics/testing/overview/).
