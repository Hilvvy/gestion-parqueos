from django import forms
from django.contrib.auth import get_user_model

from .models import ParkingLot, Reservation, Vehicle


class ReservationForm(forms.Form):
    parking_lot = forms.ModelChoiceField(label="Parqueo", queryset=ParkingLot.objects.all())
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


class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate", "kind", "brand", "model"]


class ProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "email"]


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
