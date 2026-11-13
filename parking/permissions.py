from .models import ParkingLot

SECURITY_GROUP = "Seguridad"
ADMIN_GROUP = "Administración"


def can_manage(user):
    return user.is_authenticated and user.has_perm("parking.manage_operations")


def user_role(user):
    names = {group.name for group in user.groups.all()}
    if user.is_superuser or ADMIN_GROUP in names:
        return "administrator"
    if SECURITY_GROUP in names:
        return "security"
    return "student"


def configure_roles():
    from django.contrib.auth.models import Group, Permission

    security, _ = Group.objects.get_or_create(name=SECURITY_GROUP)
    administrators, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
    administrators.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="parking",
            codename__in=["view_operational_report", "view_auditevent", "manage_operations"],
        )
    )
    return security, administrators


def is_security(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (
            user.is_superuser
            or can_manage(user)
            or user.groups.filter(name=SECURITY_GROUP).exists()
        )
    )


def permitted_lots(user):
    if not is_security(user):
        return ParkingLot.objects.none()
    if user.is_superuser or can_manage(user):
        return ParkingLot.objects.filter(active=True)
    return ParkingLot.objects.filter(active=True, securityassignment__officer=user)


def navigation(request):
    return {"can_access": is_security(request.user), "can_manage": can_manage(request.user)}
