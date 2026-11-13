from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .booking_rules import MAX_ADVANCE, validate_booking_window
from .models import ParkingLot, ParkingPolicy, Reservation, Subject, UserProfile, Vehicle
from .validators import institutional_email


class InstitutionalEmailField(forms.EmailField):
    def clean(self, value):
        return institutional_email(super().clean(value))


class ReservationForm(forms.Form):
    purpose = forms.ChoiceField(label="Motivo", choices=Reservation.Purpose.choices, required=False)
    parking_lot = forms.ModelChoiceField(
        label="Parqueo",
        queryset=ParkingLot.objects.filter(active=True),
        required=False,
        empty_label="Asignación recomendada",
    )
    vehicle = forms.ModelChoiceField(label="Vehículo", queryset=Vehicle.objects.none())
    starts_at = forms.DateTimeField(
        label="Desde",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    ends_at = forms.DateTimeField(
        label="Hasta",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].queryset = Vehicle.objects.filter(owner=user, active=True)
        self.fields["starts_at"].widget.attrs["max"] = timezone.localtime(
            timezone.now() + MAX_ADVANCE
        ).strftime("%Y-%m-%dT%H:%M")

    def clean(self):
        data = super().clean()
        if data.get("starts_at") and data.get("ends_at"):
            validate_booking_window(data["starts_at"], data["ends_at"])
        return data

    def clean_purpose(self):
        return self.cleaned_data.get("purpose") or Reservation.Purpose.CLASS


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "kind", "brand", "model", "year"]


class LoginForm(AuthenticationForm):
    username = InstitutionalEmailField(
        label="Correo institucional",
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "schinchillad502@ulacit.ed.cr",
            }
        ),
    )


class ProfileForm(forms.ModelForm):
    email = InstitutionalEmailField(label="Correo institucional")

    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["national_id", "birth_date", "career"]
        widgets = {"birth_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.national_id:
            self.fields["national_id"].disabled = True

    def clean_birth_date(self):
        value = self.cleaned_data.get("birth_date")
        if value and value > timezone.localdate():
            raise forms.ValidationError("La fecha de nacimiento no puede estar en el futuro.")
        return value


class AccountForm(forms.ModelForm):
    username = forms.CharField(required=False, max_length=150, widget=forms.HiddenInput)
    email = InstitutionalEmailField(label="Correo institucional")
    role = forms.ChoiceField(
        label="Rol",
        choices=[
            ("student", "Estudiante"),
            ("security", "Seguridad"),
            ("administrator", "Administración"),
        ],
    )
    password = forms.CharField(
        label="Contraseña inicial", required=False, widget=forms.PasswordInput
    )
    national_id = forms.CharField(label="Cédula", max_length=30, required=False)
    birth_date = forms.DateField(
        label="Fecha de nacimiento",
        required=False,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    career = forms.CharField(label="Carrera", max_length=150, required=False)
    shift = forms.ChoiceField(
        label="Jornada", required=False, choices=[("", "—"), *UserProfile.Shift.choices]
    )
    work_start = forms.TimeField(
        label="Inicio de jornada",
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    work_end = forms.TimeField(
        label="Fin de jornada",
        required=False,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
    )
    parking_lots = forms.ModelMultipleChoiceField(
        label="Parqueos asignados (Seguridad)",
        required=False,
        queryset=ParkingLot.objects.filter(active=True),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = get_user_model()
        fields = ["username", "first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields.pop("password")
            self.fields["username"].disabled = True

    def clean(self):
        data = super().clean()
        if not data.get("username") and data.get("email"):
            data["username"] = data["email"]
        if not self.instance.pk:
            if not data.get("password"):
                self.add_error("password", "La contraseña es obligatoria.")
            else:
                validate_password(data["password"], self.instance)
        if data.get("birth_date") and data["birth_date"] > timezone.localdate():
            self.add_error("birth_date", "La fecha de nacimiento no puede estar en el futuro.")
        if data.get("role") == "security" and not data.get("parking_lots"):
            self.add_error("parking_lots", "Asigna al menos un parqueo al oficial.")
        if data.get("role") == "security" and not data.get("shift"):
            self.add_error("shift", "Selecciona la jornada del oficial.")
        if data.get("role") == "security" and (
            not data.get("work_start") or not data.get("work_end")
        ):
            self.add_error("work_start", "Registra el horario del oficial.")
        if bool(data.get("work_start")) != bool(data.get("work_end")):
            self.add_error("work_end", "Completa ambas horas de jornada.")
        return data


class ParkingLotForm(forms.ModelForm):
    class Meta:
        model = ParkingLot
        fields = ["name", "capacity", "active"]


class PolicyForm(forms.ModelForm):
    class Meta:
        model = ParkingPolicy
        fields = ["arrival_tolerance_minutes"]


class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ["name", "weekday", "start_time", "end_time", "first_date", "weeks"]
        widgets = {
            "start_time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "end_time": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "first_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        }


class IntervalForm(forms.Form):
    starts_at = forms.DateTimeField(input_formats=["%Y-%m-%dT%H:%M"])
    ends_at = forms.DateTimeField(input_formats=["%Y-%m-%dT%H:%M"])

    def clean(self):
        data = super().clean()
        if data.get("starts_at") and data.get("ends_at"):
            validate_booking_window(data["starts_at"], data["ends_at"])
        return data


class MonthForm(forms.Form):
    month = forms.DateField(
        label="Mes",
        input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
    )


class ReportFilterForm(forms.Form):
    plate = forms.CharField(label="Placa", required=False, max_length=12)
    date_from = forms.DateField(
        label="Desde", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    date_to = forms.DateField(
        label="Hasta", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    status = forms.ChoiceField(
        label="Estado", required=False, choices=[("", "Todos"), *Reservation.Status.choices]
    )

    def clean(self):
        data = super().clean()
        start, end = data.get("date_from"), data.get("date_to")
        if start and end and start > end:
            raise forms.ValidationError("La fecha final debe ser posterior o igual a la inicial.")
        return data
