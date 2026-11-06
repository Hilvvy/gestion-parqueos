from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q


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


class Reservation(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        INSIDE = "inside", "En parqueo"
        COMPLETED = "completed", "Finalizada"
        CANCELLED = "cancelled", "Cancelada"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    parking_lot = models.ForeignKey(ParkingLot, on_delete=models.PROTECT)
    plate = models.CharField("placa", max_length=12)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED)
    entered_at = models.DateTimeField(null=True, blank=True)
    exited_at = models.DateTimeField(null=True, blank=True)
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        related_name="validated_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
