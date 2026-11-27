# Comparación e integración de ParqueoU Demo v4

Revisión del 26 de noviembre de 2026. Fuente local: `ParqueoU_Demo_v4/ParqueoU_Demo_v1`; su README la identifica como versión 1.4. Se comparó su código con la v3 mediante las funciones del AST, además de revisar README, esquema, reglas y pruebas. La referencia se conserva intacta; la integración se implementó en Django.

## Cambios aprovechados

| Diferencia nueva en la v4 | Implementación en el proyecto grupal |
| --- | --- |
| Restablecimiento administrativo | Pantalla propia para asignar y confirmar una clave temporal a estudiantes o Seguridad; permisos revisados también en `PasswordService` |
| Cierre de sesiones tras restablecer | Invalidación nativa de Django al cambiar el hash de contraseña; comprobada con dos sesiones previas |
| Cambio obligatorio de clave temporal | Bandera persistente en `UserProfile` y middleware que bloquea pantallas, administración de Django y API hasta sustituirla; permite cambio y cierre de sesión |
| Confirmación web del QR | URL con UUID aleatorio, página pública de datos mínimos y QR generado localmente con Segno |
| Privacidad de la confirmación | Solo estado, parqueo, horario, límite de ingreso y placa parcial. La vista no entrega el objeto de reserva al template; sin identidad, datos del visitante ni justificación excepcional |
| Validación mínima de contraseña | Formularios y validadores nativos de Django, confirmación y rechazo de reutilizar la clave actual |

Se agregó además **Mi perfil → Cambiar contraseña** para que cualquier cuenta pueda cambiar su clave conociendo la actual. Conserva la sesión actual e invalida las demás. Ambas operaciones crean auditoría de actor y cuenta afectada, sin guardar ni mostrar las claves.

La página pública es de consulta: no valida ingresos. Refleja cancelaciones, finalizaciones y vencimientos, incluso cuando el procesador de ausencias todavía no actualizó el registro. Sus respuestas usan `no-store`, `no-referrer`, exclusión de indexación y una política de contenido sin scripts. El QR privado sigue requiriendo sesión y deja de emitirse cuando ya no es válido. La consola acepta tanto la URL nueva como UUID previos y no abre enlaces externos para interpretarlos.

## Reglas que se conservan

- Correo `@ulacit.ed.cr` y cuentas demo del repositorio; no se importan las cuentas `@parqueou.ac.cr` ni sus contraseñas.
- Inicio con máximo 48 horas de anticipación, sin imponer el mínimo de 12 horas ni el máximo de 72 de la demo.
- Franjas dentro de clases para reservas regulares; visitantes mediante el flujo administrativo existente.
- Tres parqueos iniciales administrables, cupo real por intervalo y control físico de ingreso/salida.
- Sin imponer un vehículo por tipo, duraciones fijas o cancelación con una hora mínima.
- Diseño Material/Metro morado, servicios transaccionales, migraciones, roles/asignaciones, reportes Excel y operación sin conexión existentes.

La v4 no aporta implementaciones adicionales para Docker/SQL Server, lista de espera operativa, visitantes, excepciones u operación sin conexión. TT-01 y TT-02 permanecen pendientes por acuerdo previo.

## Verificación

- 25 pruebas nuevas de servicio/HTTP: autorización, contraseñas débiles o repetidas, confirmación, CSRF, rollback con fallo de auditoría, sesiones revocadas, sesión propia conservada, bloqueo obligatorio, privacidad, estados públicos y compatibilidad de búsqueda por URL/UUID.
- Suite completa: 172 pruebas Python y cinco pruebas Node aprobadas, con Ruff/formato y migraciones al día.
- Chrome real en modo headless, con base y servidor temporales: confirmación pública sin sesión; restablecimiento desde Administración; sesión previa redirigida a login; clave temporal obligada a cambiar antes de reservar; acceso posterior conservado. Se repite el recorrido de desconexión y sincronización existente.
- `python scripts/check_offline_browser.py` reproduce el recorrido; requiere las dependencias opcionales de `requirements-browser.txt` y Chrome. `pytest -q`, Ruff y los chequeos Django verifican el conjunto del proyecto.

Como observación de la referencia, su suite contiene ocho pruebas básicas. En una ejecución conjunta aislada en Windows se obtuvieron seis aprobadas y dos errores `PermissionError` al borrar la base SQLite entre pruebas; las conexiones abiertas por la demo impidieron el reinicio. No se modificó ni reinició su base original. Esta limitación de su suite no impide aprovechar los dos flujos nuevos, que se probaron independientemente en Django.

## Actualización de una instalación existente

Respaldar `db.sqlite3`, ejecutar `python manage.py migrate` y reiniciar aplicación/procesador. La migración agrega la bandera con valor falso para perfiles existentes; no cambia claves ni obliga a cambiar las de las cuentas demo. La caché pública del service worker cambia de versión para actualizar la búsqueda de direcciones QR. Recargar las pestañas existentes después de actualizar.
