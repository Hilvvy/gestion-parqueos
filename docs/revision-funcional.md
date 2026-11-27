# Revisión funcional y de coherencia

Revisión del 26 de noviembre de 2026 sobre el incremento de la demo v4. Se utilizaron bases temporales para las pruebas; los datos de la demo no se reiniciaron.

## Problemas corregidos

| Caso encontrado | Comportamiento corregido |
| --- | --- |
| Se ofrecía cancelar una cita que ya había comenzado | Dashboard y detalle muestran Cancelar únicamente antes del inicio; se conserva la validación transaccional del servidor |
| La consola ofrecía Ingreso para una cita futura o fuera de tolerancia | Muestra la fecha desde la que se permite ingresar o Plazo vencido; Salida sigue disponible mientras el vehículo esté dentro |
| Próxima reserva podía elegir una cita fuera de tolerancia pendiente del procesador | Descarta esos registros y muestra la siguiente cita vigente |
| Los UUID de IndexedDB podían devolver salida antes que ingreso al recargar | La cola y su vista provisional se ordenan por hora; ante empate, ingreso precede a salida. Una salida pendiente ya no vuelve a ofrecer Salida |
| Una sesión invalidada dejaba datos visibles en la consola local | Un 403 limpia la copia de citas y la pantalla; conserva los movimientos asociados a su cuenta. El cierre de sesión avisa también a las otras pestañas |
| La cuenta podía cambiar entre preparar y enviar una cola | El cliente conserva la identidad del registro y el servidor comprueba que coincide con la sesión. La cola no se atribuye a otra cuenta |
| Un ingreso excepcional podía retener cupo de una inasistencia no procesada todavía | Aplica la misma liberación de ausencias que las reservas normales antes de comprobar cupos |
| Un ingreso capturado a tiempo y sincronizado después de vencer mantenía `expired_at` | Limpia esa marca al aceptar la conciliación; conserva los eventos de auditoría y la recepción de la sincronización |
| Una salida en línea podía quedar antes del ingreso si el reloj del dispositivo estaba adelantado | Se comprueba el orden de horas también en línea; se rechaza la salida hasta alcanzar la hora registrada del ingreso |
| Reglamento aceptaba tolerancia cero | Formulario y servicio exigen al menos un minuto; cero hacía prácticamente imposible llegar dentro del plazo |
| El historial de auditoría consultaba aparte la cuenta afectada por cada evento | Precarga las relaciones de cuentas y parqueos para evitar consultas repetidas |

Las horas de la consola del dispositivo se muestran explícitamente en Costa Rica, aunque el dispositivo use otra zona horaria. El servidor devuelve 400 ante datos de sincronización mal formados y 403 si la cola pertenece a otra cuenta.

## Validación reproducible

- `pytest -q`: reglas, permisos, ventanas, cupos, migraciones, concurrencia del último espacio, perfiles, usuarios, vehículos, materias, contraseñas, QR, reportes y sincronización. Se incorporaron 13 casos de regresión a los 172 anteriores.
- `node --test scripts/offline-sync.test.cjs`: ocho pruebas, incluyendo orden de IndexedDB, empate temporal y estado provisional después de una salida.
- `python scripts/check_offline_browser.py`: Chrome real con base y servidor temporales. Recorre alta de vehículo y materia, reserva con QR, cancelación, retiro, navegación móvil, paneles administrativos, reportes/Excel, desconexión y recarga, sincronización sin duplicados, recuperación de contraseña y cierre entre pestañas. Verifica que una sesión invalidada deje vacía la consola local.
- Ruff, formato, chequeos Django y comprobación de migraciones pendientes en CI.

El recorrido de navegador usa las dependencias opcionales de `requirements-browser.txt` y Chrome instalado. Las validaciones no equivalen a pruebas con hardware físico, infraestructura institucional o todos los dispositivos posibles. TT-01 y TT-02 permanecen pendientes.
