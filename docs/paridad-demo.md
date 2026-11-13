# Flujos de la demo integrados en Django

Referencia funcional: ParqueoU_Demo_v3/ParqueoU_Demo_v1 del equipo. Se mantiene un único monolito Django y el diseño Material/Metro morado. Esta matriz distingue funcionalidades incorporadas de reglas adaptadas; no declara completados todos los requisitos del proyecto final.

| Función de la demo | Implementación grupal |
| --- | --- |
| Acceso y roles | Usuario o correo, contraseña protegida, sesiones y CSRF de Django; Estudiante, Seguridad y Administración |
| Perfil personal y académico | Nombre, apellidos, correo, cédula, nacimiento y carrera. La cédula registrada se cambia por Administración |
| Perfil del oficial | Jornada, hora inicial/final y parqueos asignados. Admite jornada nocturna que termina al día siguiente |
| Vehículos | Tipo, placa, marca, modelo y año; registro/retiro, propiedad, historial y reemplazo sin bloquear por registros inactivos |
| Materias y horarios | Registro semanal de 1–16 semanas por estudiante o administrador; fechas concretas, fuente autodeclarada identificada, retiro sin borrar historia |
| Solicitud de reserva | Vehículo propio, motivo de curso/trámite/evento, inicio y fin dentro de clases activas; validación de traslapes y cupo |
| Recomendación de parqueo | Mayor número de cupos libres para la franja. Consulta visual y asignación final dentro de la transacción |
| Confirmación | Código UUID, QR local, detalle y cancelación; código inválido al cancelar, vencer o haber ingresado |
| Historial del estudiante | Reservas conservadas con estados y detalle |
| Próxima visita | Fecha, parqueo, placa, límite de ingreso y cuenta regresiva actualizada cada segundo |
| Seguridad | Búsqueda por placa/código, detalle autorizado, ingreso/salida, hora y oficial, rechazo fuera de horario/tolerancia y con parqueo lleno |
| Alertas operativas | Próximos 30 minutos y pendientes de ingreso; actualizadas cada cinco segundos, solo para parqueos autorizados |
| Disponibilidad | Cupo físico por parqueo activo, actualizado cada cinco segundos; distingue reservas futuras de vehículos dentro |
| Ausencias | Tolerancia configurable, procesador independiente cada 15 segundos, estado Vencida y auditoría idempotente |
| Administración de usuarios | Crear/editar, rol, perfiles, asignaciones y activar/desactivar; conserva historial y revoca sesiones de inactivos |
| Administración de parqueos | Crear/editar capacidad y estado activo; protege ocupación y reservas comprometidas |
| Reglamento | Tolerancia editable en la app; cada reserva conserva el plazo con que se confirmó |
| Reportes | Historial por placa/fechas/estado y CSV del mismo conjunto con protección ante fórmulas |
| Indicadores mensuales | Reservas, cancelaciones, parqueo más solicitado, hora local de mayor demanda y cantidades por estado |
| Auditoría | Reserva, cancelación, entrada/salida, ausencia, vehículos, perfiles, usuarios, parqueos, materias y reglamento |
| Ejecución y pruebas | Migraciones, semilla sin borrado, arranque web/procesador, suite aislada y GitHub Actions |

## Reglas conservadas del proyecto grupal

- Tres parqueos iniciales; se pueden administrar otros desde la app. No se fijan cinco ni 50 espacios obligatorios por parqueo.
- Reserva dentro de clases activas para todos los motivos. No se incorpora anticipación obligatoria de 12–72 horas ni duración fija de 4/2/3 horas.
- Cancelación antes del inicio, sin requerir una hora de anticipación.
- Vehículos activos propios, sin imponer el límite no acordado de uno por tipo.
- Tolerancia inicial demo de 15 minutos, editable por Administración.
- Los horarios autodeclarados permiten demostrar el flujo del compañero. No equivalen a horarios institucionales verificados.

La demo recibida solo incluía una tabla y un mensaje para lista de espera, sin flujo implementado; no se declara esa funcionalidad como existente. Ninguna de las dos versiones incluye lector de cámara, acceso sin conexión con sincronización, visitantes autorizados ni hardware. En el proyecto grupal siguen pendientes además Docker/SQL Server y mediciones de rendimiento.

Las pruebas cubren el recorrido estudiante → materia → vehículo → reserva recomendada → QR → ingreso/salida → reportes y auditoría, además de permisos, validaciones, migración y concurrencia.
