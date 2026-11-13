import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .validators import normalize_plate


class ParkingLot(models.Model):
    name = models.CharField("nombre", max_length=80, unique=True)
    capacity = models.PositiveIntegerField("capacidad")
    active = models.BooleanField("activo", default=True)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(capacity__gte=1), name="positive_capacity")
        ]

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    class Shift(models.TextChoices):
        DAY = "day", "Diurna"
        MIXED = "mixed", "Mixta"
        NIGHT = "night", "Nocturna"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    national_id = models.CharField("cédula", max_length=30, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    career = models.CharField("carrera", max_length=150, blank=True)
    shift = models.CharField("jornada", choices=Shift.choices, max_length=10, blank=True)
    work_start = models.TimeField("inicio de jornada", null=True, blank=True)
    work_end = models.TimeField("fin de jornada", null=True, blank=True)

    class Meta:
        permissions = [("manage_operations", "Puede administrar usuarios y parqueos")]
        constraints = [
            models.UniqueConstraint(
                fields=["national_id"],
                condition=~Q(national_id=""),
                name="unique_nonempty_national_id",
            )
        ]

    def __str__(self):
        return str(self.user)

    def clean(self):
        if self.birth_date and self.birth_date > timezone.localdate():
            raise ValidationError("La fecha de nacimiento no puede estar en el futuro.")
        if bool(self.work_start) != bool(self.work_end):
            raise ValidationError("Completa ambas horas de jornada.")


class Subject(models.Model):
    WEEKDAYS = [
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="registered_subjects"
    )
    name = models.CharField("materia", max_length=100)
    weekday = models.PositiveSmallIntegerField("día", choices=WEEKDAYS)
    start_time = models.TimeField("hora inicial")
    end_time = models.TimeField("hora final")
    first_date = models.DateField("a partir de")
    weeks = models.PositiveSmallIntegerField(
        "semanas", default=12, validators=[MinValueValidator(1), MaxValueValidator(16)]
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")), name="subject_valid_times"
            )
        ]

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("La hora final debe ser posterior a la inicial.")

    def __str__(self):
        return self.name


class ClassSchedule(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.CharField("curso", max_length=100)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, null=True, blank=True)
    active = models.BooleanField(default=True)

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
    year = models.PositiveSmallIntegerField(
        "año", null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
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
    class Purpose(models.TextChoices):
        CLASS = "class", "Curso presencial"
        APPOINTMENT = "appointment", "Trámite o cita"
        EVENT = "event", "Evento o charla"

    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        INSIDE = "inside", "En parqueo"
        COMPLETED = "completed", "Finalizada"
        CANCELLED = "cancelled", "Cancelada"
        EXPIRED = "expired", "Vencida"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    parking_lot = models.ForeignKey(ParkingLot, on_delete=models.PROTECT)
    plate = models.CharField("placa", max_length=12)
    purpose = models.CharField(
        "motivo", max_length=12, choices=Purpose.choices, default=Purpose.CLASS
    )
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
        USER_CREATED = "user_created", "Usuario creado"
        USER_UPDATED = "user_updated", "Usuario actualizado"
        USER_STATE = "user_state", "Estado de usuario"
        LOT_UPDATED = "lot_updated", "Parqueo actualizado"
        SUBJECT_ADDED = "subject_added", "Materia registrada"
        SUBJECT_RETIRED = "subject_retired", "Materia retirada"
        POLICY_UPDATED = "policy_updated", "Reglamento actualizado"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True)
    subject_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="received_audit_events",
    )
    parking_lot = models.ForeignKey(ParkingLot, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=24, choices=Action.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
