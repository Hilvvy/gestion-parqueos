from django import forms

from .models import ParkingLot


class ReservationForm(forms.Form):
    parking_lot = forms.ModelChoiceField(label="Parqueo", queryset=ParkingLot.objects.all())
    plate = forms.CharField(
        label="Placa", max_length=12, widget=forms.TextInput(attrs={"placeholder": "ABC123"})
    )
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
