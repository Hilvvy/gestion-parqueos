from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .capacity import peak_occupancy
from .models import (
    AuditEvent,
    ClassSchedule,
    ParkingLot,
    ParkingPolicy,
    Reservation,
    SecurityAssignment,
    Subject,
    UserProfile,
)
from .permissions import can_manage, configure_roles

PROFILE_FIELDS = ("national_id", "birth_date", "career", "shift", "work_start", "work_end")
ACCOUNT_FIELDS = ("username", "first_name", "last_name", "email")


def validate_email_ownership(user):
    user.email = user.email.strip().lower()
    if (
        user.email
        and get_user_model().objects.filter(email__iexact=user.email).exclude(pk=user.pk).exists()
    ):
        raise ValidationError("El correo ya pertenece a otro usuario.")


class ProfileService:
    @staticmethod
    @transaction.atomic
    def update(*, actor, account_data, profile_data):
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if (
            profile.national_id
            and profile_data.get("national_id", profile.national_id) != profile.national_id
        ):
            raise ValidationError("Solicita a Administración el cambio de cédula.")
        for field in ("first_name", "last_name", "email"):
            setattr(user, field, account_data[field])
        for field in ("national_id", "birth_date", "career"):
            setattr(profile, field, profile_data.get(field, getattr(profile, field)))
        user.full_clean()
        validate_email_ownership(user)
        profile.full_clean()
        user.save(update_fields=["first_name", "last_name", "email"])
        profile.save()
        AuditEvent.objects.create(
            actor=actor, subject_user=user, action=AuditEvent.Action.PROFILE_UPDATED
        )


class AdministrationService:
    @staticmethod
    def require_manager(actor):
        if not can_manage(actor):
            raise PermissionDenied

    @classmethod
    @transaction.atomic
    def save_account(cls, *, actor, data, user_id=None):
        cls.require_manager(actor)
        User = get_user_model()
        user = User.objects.select_for_update().get(pk=user_id) if user_id else User()
        if user.is_superuser and not actor.is_superuser:
            raise PermissionDenied
        role = data["role"]
        if role not in ("student", "security", "administrator"):
            raise ValidationError("Rol inválido.")
        if user.is_superuser and role != "administrator":
            raise ValidationError("La cuenta de superusuario conserva el rol de Administración.")
        if user.pk == actor.pk and not actor.is_superuser and role != "administrator":
            raise ValidationError("No puedes retirar tu propio acceso administrativo.")
        lots = list(data.get("parking_lots", []))
        if role == "security" and (not lots or any(not lot.active for lot in lots)):
            raise ValidationError("Asigna al menos un parqueo activo al oficial.")
        if role == "security" and not all(
            data.get(field) for field in ("shift", "work_start", "work_end")
        ):
            raise ValidationError("Registra la jornada y el horario del oficial.")
        created = not user.pk
        for field in ACCOUNT_FIELDS:
            setattr(user, field, data[field])
        if created:
            validate_password(data.get("password", ""), user)
            user.set_password(data["password"])
        user.full_clean()
        validate_email_ownership(user)
        user.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)
        for field in PROFILE_FIELDS:
            setattr(profile, field, data.get(field, getattr(profile, field)))
        profile.full_clean()
        profile.save()
        security, administrators = configure_roles()
        user.groups.remove(security, administrators)
        if role == "security":
            user.groups.add(security)
        elif role == "administrator":
            user.groups.add(administrators)
        SecurityAssignment.objects.filter(officer=user).delete()
        if role == "security":
            SecurityAssignment.objects.bulk_create(
                [SecurityAssignment(officer=user, parking_lot=lot) for lot in lots]
            )
        AuditEvent.objects.create(
            actor=actor,
            subject_user=user,
            action=AuditEvent.Action.USER_CREATED if created else AuditEvent.Action.USER_UPDATED,
        )
        return user

    @classmethod
    @transaction.atomic
    def toggle_account(cls, *, actor, user_id):
        cls.require_manager(actor)
        user = get_user_model().objects.select_for_update().get(pk=user_id)
        if user.pk == actor.pk:
            raise ValidationError("No puedes desactivar tu propia cuenta.")
        if user.is_superuser and not actor.is_superuser:
            raise PermissionDenied
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        AuditEvent.objects.create(
            actor=actor, subject_user=user, action=AuditEvent.Action.USER_STATE
        )

    @classmethod
    @transaction.atomic
    def save_lot(cls, *, actor, data, lot_id=None):
        cls.require_manager(actor)
        lot = ParkingLot.objects.select_for_update().get(pk=lot_id) if lot_id else ParkingLot()
        if lot.pk:
            now = timezone.now()
            active = Reservation.objects.filter(parking_lot=lot).filter(
                models_active_reservations(now)
            )
            if not data["active"] and active.exists():
                raise ValidationError(
                    "No puedes desactivar un parqueo con reservas pendientes o vehículos dentro."
                )
            inside = active.filter(status=Reservation.Status.INSIDE).count()
            rows = list(active.values_list("starts_at", "ends_at"))
            peak = peak_occupancy(
                rows, now, max((end for _, end in rows), default=now + timedelta(seconds=1))
            )
            if data["capacity"] < max(inside, peak):
                raise ValidationError(
                    "La capacidad no puede ser menor que la ocupación o las reservas comprometidas."
                )
        for field in ("name", "capacity", "active"):
            setattr(lot, field, data[field])
        lot.full_clean()
        lot.save()
        AuditEvent.objects.create(
            actor=actor, parking_lot=lot, action=AuditEvent.Action.LOT_UPDATED
        )
        return lot

    @classmethod
    @transaction.atomic
    def save_policy(cls, *, actor, minutes):
        cls.require_manager(actor)
        policy, _ = ParkingPolicy.objects.get_or_create(pk=1)
        policy.arrival_tolerance_minutes = minutes
        policy.full_clean()
        policy.save()
        AuditEvent.objects.create(actor=actor, action=AuditEvent.Action.POLICY_UPDATED)


def models_active_reservations(now):
    from django.db.models import Q

    return Q(status=Reservation.Status.INSIDE) | Q(
        status=Reservation.Status.CONFIRMED, ends_at__gt=now
    )


class SubjectService:
    @staticmethod
    def require_owner_or_manager(actor, user):
        if actor.pk != user.pk and not can_manage(actor):
            raise PermissionDenied

    @classmethod
    @transaction.atomic
    def register(cls, *, actor, user, data):
        cls.require_owner_or_manager(actor, user)
        subject = Subject(user=user, registered_by=actor, **data)
        subject.full_clean()
        duplicate = Subject.objects.filter(
            user=user,
            active=True,
            name=subject.name,
            weekday=subject.weekday,
            start_time=subject.start_time,
            first_date=subject.first_date,
        ).exists()
        if duplicate:
            raise ValidationError("Esta materia y horario ya están registrados.")
        subject.save()
        first = subject.first_date + timedelta(
            days=(subject.weekday - subject.first_date.weekday()) % 7
        )
        schedule = []
        for week in range(subject.weeks):
            day = first + timedelta(weeks=week)
            start = timezone.make_aware(datetime.combine(day, subject.start_time))
            end = timezone.make_aware(datetime.combine(day, subject.end_time))
            schedule.append(
                ClassSchedule(
                    user=user, subject=subject, course=subject.name, starts_at=start, ends_at=end
                )
            )
        ClassSchedule.objects.bulk_create(schedule)
        AuditEvent.objects.create(
            actor=actor, subject_user=user, action=AuditEvent.Action.SUBJECT_ADDED
        )
        return subject

    @classmethod
    @transaction.atomic
    def retire(cls, *, actor, subject_id):
        subject = Subject.objects.select_for_update().select_related("user").get(pk=subject_id)
        cls.require_owner_or_manager(actor, subject.user)
        if not subject.active:
            raise ValidationError("La materia ya está retirada.")
        rows = ClassSchedule.objects.filter(subject=subject)
        pending = Reservation.objects.filter(user=subject.user).filter(
            models_active_reservations(timezone.now())
        )
        for schedule in rows:
            if pending.filter(
                starts_at__gte=schedule.starts_at, ends_at__lte=schedule.ends_at
            ).exists():
                raise ValidationError(
                    "Cancela las reservas pendientes antes de retirar la materia."
                )
        subject.active = False
        subject.save(update_fields=["active"])
        rows.update(active=False)
        AuditEvent.objects.create(
            actor=actor, subject_user=subject.user, action=AuditEvent.Action.SUBJECT_RETIRED
        )
