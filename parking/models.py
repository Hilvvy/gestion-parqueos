import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from .validators import normalize_plate


class ParkingLot(models.Model):
    name = models.CharField("nombre", max_length=80, unique=True)
    capacity = models.PositiveIntegerField("capacidad")
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gte=1), name="positive_capacity")
        ]

    def __str__(self):
        return self.name


class ClassSchedule(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.CharField("curso", max_length=100)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="schedule_valid_interval"
            )
        ]

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError("El horario debe terminar después de su inicio.")

    def __str__(self):
        return self.course


class Vehicle(models.Model):
    class Kind(models.TextChoices):
        CAR = "car", "Automóvil"
        MOTORCYCLE = "motorcycle", "Motocicleta"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    plate = models.CharField("placa", max_length=12)
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    brand = models.CharField("marca", max_length=50)
    model = models.CharField("modelo", max_length=50, blank=True)
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["plate"]
        constraints = [
            models.UniqueConstraint(
                fields=["plate"], condition=Q(active=True), name="unique_active_plate"
            )
        ]

    def clean(self):
        self.plate = normalize_plate(self.plate)

    def __str__(self):
        return f"{self.plate} · {self.get_kind_display()}"


class SecurityAssignment(models.Model):
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    parking_lot = models.ForeignKey(ParkingLot, on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["officer", "parking_lot"], name="unique_officer_lot")
        ]

    def __str__(self):
        return f"{self.officer} · {self.parking_lot}"


class ParkingPolicy(models.Model):
    arrival_tolerance_minutes = models.PositiveSmallIntegerField(
        "tolerancia de llegada en minutos", default=15
    )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "Reglamento de parqueos"


class Reservation(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        INSIDE = "inside", "En parqueo"
        COMPLETED = "completed", "Finalizada"
        CANCELLED = "cancelled", "Cancelada"
        EXPIRED = "expired", "Vencida"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    parking_lot = models.ForeignKey(ParkingLot, on_delete=models.PROTECT)
    plate = models.CharField("placa", max_length=12)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True)
    code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED)
    entered_at = models.DateTimeField(null=True, blank=True)
    exited_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    expired_at = models.DateTimeField(null=True, blank=True)
    entry_deadline = models.DateTimeField(null=True, blank=True)
    exit_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="validated_exits",
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        related_name="validated_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("view_operational_report", "Puede consultar reportes operativos")]
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="reservation_valid_interval"
            )
        ]
        indexes = [
            models.Index(fields=["parking_lot", "status", "starts_at", "ends_at"]),
            models.Index(fields=["plate", "status"]),
        ]

    def __str__(self):
        return f"{self.plate} · {self.parking_lot}"


class AuditEvent(models.Model):
    class Action(models.TextChoices):
        RESERVED = "reserved", "Reserva creada"
        CANCELLED = "cancelled", "Reserva cancelada"
        ENTERED = "entered", "Ingreso"
        EXITED = "exited", "Salida"
        EXPIRED = "expired", "Inasistencia"
        VEHICLE_ADDED = "vehicle_added", "Vehículo registrado"
        VEHICLE_RETIRED = "vehicle_retired", "Vehículo retirado"
        PROFILE_UPDATED = "profile_updated", "Perfil actualizado"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=24, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
