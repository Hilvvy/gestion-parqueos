# Validación de acceso, historial y desconexión

Medición local realizada el 12 de noviembre de 2026. Reproducir con `python scripts/benchmark_access.py`. El script crea y elimina su propia base SQLite temporal, con 10.000 reservas históricas, un parqueo y 30 ingresos adicionales. No usa la base de la demo.

Entorno: Windows AMD64, Python 3.12.4, Django 5.2.19, SQLite. Treinta muestras después de una consulta de calentamiento; sesión ya autenticada. Se usa Django Client con renderizado de plantilla, servicios y base de datos reales. El historial filtra placa y rango de fechas y renderiza hasta 200 resultados. El ingreso mide juntos la búsqueda HTTP por placa y el POST de validación, incluyendo lectura posterior para comprobar el estado.

| Operación | Mediana | P95 | Máximo observado | Objetivo del backlog |
| --- | ---: | ---: | ---: | ---: |
| Historial filtrado | 0,1844 s | 0,2322 s | 0,3146 s | <5 s |
| Buscar y validar ingreso | 0,0456 s | 0,0624 s | 0,0687 s | <10 s |

Los resultados cumplen los objetivos en esta medición local. Excluyen latencia de red, descarga/renderizado del navegador, lectura física de QR e interacción humana. No representan una prueba de carga concurrente ni una garantía para SQL Server o infraestructura institucional. Los controles funcionales y de concurrencia se ejecutan por separado en pytest. No se añaden umbrales temporales frágiles a CI.

## Evidencia funcional

- 147 pruebas Python aprobadas, incluyendo autorización de visitantes, capacidad compartida, QR privado, excepciones justificadas, exportación, control de asignación, límites de reloj, CSRF, sincronización posterior a vencimiento y repetición del mismo UUID sin repetir auditoría.
- Cinco pruebas Node de la cola: orden, aislamiento por cuenta, reintento del mismo identificador al perder la respuesta, conflicto visible y sesión vencida.
- `python scripts/check_offline_browser.py`: Chrome real en modo headless con service worker e IndexedDB. Autentica un oficial en un servidor/base temporales, prepara la consola, corta la red, recarga, guarda ingreso, recarga otra vez, guarda salida y comprueba que todavía no hay movimientos en servidor. Restaura la red, espera sincronización automática y verifica dos movimientos aceptados y un solo evento de auditoría por transición. Repetir sincronización no agrega registros. También comprueba la página de respaldo de `/acceso/` sin red.

Los movimientos sin conexión son provisionales hasta validarse en servidor. La disponibilidad observada en el dispositivo puede quedar desactualizada; los conflictos se muestran al oficial. Se requiere sincronizar en 24 horas y conservar la página abierta para la reconexión automática. La validación en dispositivos del equipo sigue siendo parte de la revisión de aceptación.

TT-01 (Docker/SQL Server) y TT-02 (diagramas/ADR) se mantienen para el final por acuerdo del equipo.
