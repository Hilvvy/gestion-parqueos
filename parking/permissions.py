from .models import ParkingLot

SECURITY_GROUP = "Seguridad"


def is_security(user):
    return bool(
        user.is_authenticated
        and user.is_active
        and (user.is_superuser or user.groups.filter(name=SECURITY_GROUP).exists())
    )


def permitted_lots(user):
    if not is_security(user):
        return ParkingLot.objects.none()
    if user.is_superuser:
        return ParkingLot.objects.all()
    return ParkingLot.objects.filter(securityassignment__officer=user)


def navigation(request):
    return {"can_access": is_security(request.user)}
