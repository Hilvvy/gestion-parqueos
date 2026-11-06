from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reservar/", views.reserve, name="reserve"),
    path("reservas/<int:pk>/cancelar/", views.cancel, name="cancel"),
    path("acceso/", views.access_console, name="access"),
    path("acceso/<int:pk>/<str:action>/", views.movement, name="movement"),
    path("disponibilidad/", views.availability, name="availability"),
]
