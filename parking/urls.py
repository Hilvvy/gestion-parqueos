from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reservar/", views.reserve, name="reserve"),
    path("reservas/<uuid:code>/", views.reservation_detail, name="reservation_detail"),
    path("reservas/<uuid:code>/qr.svg", views.reservation_qr, name="reservation_qr"),
    path("reservas/<int:pk>/cancelar/", views.cancel, name="cancel"),
    path("acceso/", views.access_console, name="access"),
    path("acceso/<int:pk>/<str:action>/", views.movement, name="movement"),
    path("disponibilidad/", views.availability, name="availability"),
    path("vehiculos/", views.vehicles, name="vehicles"),
    path("vehiculos/<int:pk>/retirar/", views.retire_vehicle, name="retire_vehicle"),
    path("perfil/", views.profile, name="profile"),
    path("reportes/", views.reports, name="reports"),
    path("reportes.csv", views.report_csv, name="report_csv"),
    path("auditoria/", views.audit_log, name="audit"),
]
