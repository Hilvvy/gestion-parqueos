from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .administration import SubjectService
from .forms import SubjectForm
from .models import ClassSchedule, Subject


def subject_page(request, target):
    form = SubjectForm(
        request.POST or None, initial={"first_date": timezone.localdate(), "weeks": 12}
    )
    if request.method == "POST" and form.is_valid():
        try:
            SubjectService.register(actor=request.user, user=target, data=form.cleaned_data)
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
        else:
            messages.success(request, "Materia y horarios semanales registrados.")
            return (
                redirect("manage_subjects", pk=target.pk)
                if target.pk != request.user.pk
                else redirect("subjects")
            )
    subjects = Subject.objects.filter(user=target, active=True).select_related("registered_by")
    schedules = ClassSchedule.objects.filter(
        user=target, active=True, ends_at__gt=timezone.now()
    ).order_by("starts_at")[:30]
    return render(
        request,
        "parking/subjects.html",
        {"form": form, "subjects": subjects, "schedules": schedules, "target": target},
    )


@login_required
@never_cache
def subjects(request):
    return subject_page(request, request.user)


@permission_required("parking.manage_operations", raise_exception=True)
@never_cache
def manage_subjects(request, pk):
    return subject_page(request, get_object_or_404(get_user_model(), pk=pk))


@login_required
@require_POST
def retire_subject(request, pk):
    subject = get_object_or_404(Subject, pk=pk)
    try:
        SubjectService.retire(actor=request.user, subject_id=pk)
    except ValidationError as error:
        messages.error(request, error.messages[0])
    else:
        messages.success(request, "Materia retirada; se conserva el historial.")
    return (
        redirect("manage_subjects", pk=subject.user_id)
        if subject.user_id != request.user.pk
        else redirect("subjects")
    )
