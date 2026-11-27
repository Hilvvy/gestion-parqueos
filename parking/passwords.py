from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .administration import AdministrationService
from .models import AuditEvent, UserProfile
from .permissions import can_manage, user_role


class PasswordService:
    @staticmethod
    @transaction.atomic
    def reset(*, actor, user_id, temporary_password):
        AdministrationService.require_manager(actor)
        user = get_user_model().objects.select_for_update().get(pk=user_id)
        if user.is_superuser or can_manage(user) or user_role(user) == "administrator":
            raise PermissionDenied("Administración cambia su clave desde Mi perfil.")
        validate_password(temporary_password, user)
        if user.check_password(temporary_password):
            raise ValidationError("La contraseña temporal debe ser diferente de la actual.")
        # El cambio de hash invalida las sesiones anteriores mediante Django.
        user.set_password(temporary_password)
        user.save(update_fields=["password"])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.must_change_password = True
        profile.save(update_fields=["must_change_password"])
        AuditEvent.objects.create(
            actor=actor, subject_user=user, action=AuditEvent.Action.PASSWORD_RESET
        )

    @staticmethod
    @transaction.atomic
    def change(*, actor, old_password, new_password):
        if not actor.is_authenticated or not actor.is_active:
            raise PermissionDenied
        user = get_user_model().objects.select_for_update().get(pk=actor.pk)
        if not user.check_password(old_password):
            raise ValidationError("La contraseña actual no es correcta.")
        validate_password(new_password, user)
        if user.check_password(new_password):
            raise ValidationError("La nueva contraseña debe ser diferente de la actual.")
        user.set_password(new_password)
        user.save(update_fields=["password"])
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.must_change_password = False
        profile.save(update_fields=["must_change_password"])
        AuditEvent.objects.create(
            actor=user, subject_user=user, action=AuditEvent.Action.PASSWORD_CHANGED
        )
        return user
