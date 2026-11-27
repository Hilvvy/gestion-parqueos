from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters

from .models import UserProfile
from .passwords import PasswordService
from .permissions import can_manage, user_role


@sensitive_post_parameters()
@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def password_reset(request, pk):
    target = get_object_or_404(get_user_model(), pk=pk)
    if target.is_superuser or can_manage(target) or user_role(target) == "administrator":
        raise PermissionDenied
    form = SetPasswordForm(target, request.POST or None)
    form.fields["new_password1"].label = "Contraseña temporal"
    form.fields["new_password2"].label = "Confirmar contraseña temporal"
    if request.method == "POST" and form.is_valid():
        try:
            PasswordService.reset(
                actor=request.user,
                user_id=pk,
                temporary_password=form.cleaned_data["new_password1"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request,
                "Contraseña restablecida. Las sesiones anteriores quedan invalidadas; la cuenta deberá cambiarla al ingresar.",
            )
            return redirect("manage_accounts")
    return render(request, "parking/password_reset.html", {"form": form, "target": target})


@sensitive_post_parameters()
@login_required
@never_cache
def password_change(request):
    forced = UserProfile.objects.filter(user=request.user, must_change_password=True).exists()
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            user = PasswordService.change(
                actor=request.user,
                old_password=form.cleaned_data["old_password"],
                new_password=form.cleaned_data["new_password1"],
            )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            update_session_auth_hash(request, user)
            messages.success(
                request, "Contraseña actualizada. Las demás sesiones quedan invalidadas."
            )
            return redirect("dashboard")
    return render(request, "parking/password_change.html", {"form": form, "forced": forced})
