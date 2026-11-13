from django.urls import path

from . import management_views, subject_views, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reservar/", views.reserve, name="reserve"),
    path("recomendacion/", views.recommendation, name="recommendation"),
    path("reservas/<uuid:code>/", views.reservation_detail, name="reservation_detail"),
    path("reservas/<uuid:code>/qr.svg", views.reservation_qr, name="reservation_qr"),
    path("reservas/<int:pk>/cancelar/", views.cancel, name="cancel"),
    path("acceso/", views.access_console, name="access"),
    path("acceso/alertas/", views.alerts_data, name="alerts_data"),
    path("acceso/<int:pk>/<str:action>/", views.movement, name="movement"),
    path("disponibilidad/", views.availability, name="availability"),
    path("vehiculos/", views.vehicles, name="vehicles"),
    path("vehiculos/<int:pk>/retirar/", views.retire_vehicle, name="retire_vehicle"),
    path("perfil/", views.profile, name="profile"),
    path("materias/", subject_views.subjects, name="subjects"),
    path("materias/<int:pk>/retirar/", subject_views.retire_subject, name="retire_subject"),
    path("reportes/", views.reports, name="reports"),
    path("reportes.csv", views.report_csv, name="report_csv"),
    path("auditoria/", views.audit_log, name="audit"),
    path("indicadores/", views.indicators, name="indicators"),
    path("gestion/usuarios/", management_views.accounts, name="manage_accounts"),
    path("gestion/usuarios/nuevo/", management_views.account_edit, name="manage_account_create"),
    path("gestion/usuarios/<int:pk>/", management_views.account_edit, name="manage_account_edit"),
    path(
        "gestion/usuarios/<int:pk>/estado/",
        management_views.account_toggle,
        name="manage_account_toggle",
    ),
    path(
        "gestion/usuarios/<int:pk>/materias/", subject_views.manage_subjects, name="manage_subjects"
    ),
    path("gestion/parqueos/", management_views.lots, name="manage_lots"),
    path("gestion/parqueos/nuevo/", management_views.lot_edit, name="manage_lot_create"),
    path("gestion/parqueos/<int:pk>/", management_views.lot_edit, name="manage_lot_edit"),
    path("gestion/reglamento/", management_views.policy, name="manage_policy"),
]
