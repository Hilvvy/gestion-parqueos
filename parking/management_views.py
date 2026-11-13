from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .administration import PROFILE_FIELDS, AdministrationService
from .forms import AccountForm, ParkingLotForm, PolicyForm
from .models import ParkingLot, ParkingPolicy, Reservation
from .permissions import user_role


def add_errors(form, error):
    for message in error.messages:
        form.add_error(None, message)


@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def dashboard(request):
    users = get_user_model().objects.filter(is_active=True)
    return render(
        request,
        "parking/management/dashboard.html",
        {
            "active_users": users.count(),
            "officers": users.filter(groups__name="Seguridad").count(),
            "active_lots": ParkingLot.objects.filter(active=True).count(),
            "inside": Reservation.objects.filter(status=Reservation.Status.INSIDE).count(),
        },
    )


@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def accounts(request):
    query = request.GET.get("q", "").strip()
    users = (
        get_user_model()
        .objects.select_related("userprofile")
        .prefetch_related("groups")
        .order_by("username")
    )
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )
    page = Paginator(users, 30).get_page(request.GET.get("page"))
    labels = {"student": "Estudiante", "security": "Seguridad", "administrator": "Administración"}
    for user in page:
        user.role_label = labels[user_role(user)]
    return render(request, "parking/management/accounts.html", {"page": page, "query": query})


@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def account_edit(request, pk=None):
    target = get_object_or_404(get_user_model(), pk=pk) if pk else None
    if target and target.is_superuser and not request.user.is_superuser:
        raise PermissionDenied
    initial = {"role": user_role(target) if target else "student"}
    if target:
        profile = getattr(target, "userprofile", None)
        if profile:
            initial.update({field: getattr(profile, field) for field in PROFILE_FIELDS})
        initial["parking_lots"] = ParkingLot.objects.filter(securityassignment__officer=target)
    form = AccountForm(request.POST or None, instance=target, initial=initial)
    if target and target.is_superuser:
        form.fields["role"].disabled = True
    if request.method == "POST" and form.is_valid():
        try:
            AdministrationService.save_account(
                actor=request.user, data=form.cleaned_data, user_id=pk
            )
        except ValidationError as error:
            add_errors(form, error)
        except IntegrityError:
            form.add_error(None, "El usuario o la cédula ya están registrados.")
        else:
            messages.success(request, "Usuario guardado.")
            return redirect("manage_accounts")
    return render(
        request,
        "parking/management/form.html",
        {
            "form": form,
            "title": "Editar usuario" if target else "Crear usuario",
            "back_url": "manage_accounts",
        },
    )


@permission_required("parking.manage_operations", raise_exception=True)
@require_POST
def account_toggle(request, pk):
    get_object_or_404(get_user_model(), pk=pk)
    try:
        AdministrationService.toggle_account(actor=request.user, user_id=pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Estado del usuario actualizado.")
    return redirect("manage_accounts")


@permission_required("parking.manage_operations", raise_exception=True)
def lots(request):
    return render(request, "parking/management/lots.html", {"lots": ParkingLot.objects.all()})


@permission_required("parking.manage_operations", raise_exception=True)
def lot_edit(request, pk=None):
    lot = get_object_or_404(ParkingLot, pk=pk) if pk else None
    form = ParkingLotForm(request.POST or None, instance=lot)
    if request.method == "POST" and form.is_valid():
        try:
            AdministrationService.save_lot(actor=request.user, data=form.cleaned_data, lot_id=pk)
        except ValidationError as error:
            add_errors(form, error)
        except IntegrityError:
            form.add_error(None, "El nombre del parqueo ya está registrado.")
        else:
            messages.success(request, "Parqueo guardado.")
            return redirect("manage_lots")
    return render(
        request,
        "parking/management/form.html",
        {
            "form": form,
            "title": "Editar parqueo" if lot else "Crear parqueo",
            "back_url": "manage_lots",
        },
    )


@permission_required("parking.manage_operations", raise_exception=True)
def policy(request):
    current, _ = ParkingPolicy.objects.get_or_create(pk=1)
    form = PolicyForm(request.POST or None, instance=current)
    if request.method == "POST" and form.is_valid():
        AdministrationService.save_policy(
            actor=request.user, minutes=form.cleaned_data["arrival_tolerance_minutes"]
        )
        messages.success(request, "Reglamento actualizado para las reservas nuevas.")
        return redirect("manage_policy")
    return render(
        request,
        "parking/management/form.html",
        {"form": form, "title": "Tolerancia de llegada", "back_url": "manage_lots"},
    )
