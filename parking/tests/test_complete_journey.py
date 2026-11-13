from unittest.mock import patch

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from parking.models import AuditEvent, ClassSchedule, Reservation, Vehicle
from parking.tests.test_parity import manager as manager
from parking.tests.test_parity import subject_data


def test_student_to_officer_to_administration_journey(scenario, manager):
    student = Client()
    student.force_login(scenario["user"])
    assert (
        student.post(
            reverse("vehicles"),
            {"plate": "FLOW123", "kind": "car", "brand": "Honda", "model": "Civic", "year": 2024},
        ).status_code
        == 302
    )
    vehicle = Vehicle.objects.get(plate="FLOW123")
    assert student.post(reverse("subjects"), subject_data(weeks=1)).status_code == 302
    schedule = ClassSchedule.objects.filter(subject__name="Calidad semanal").get()
    dates = {
        "starts_at": timezone.localtime(schedule.starts_at).strftime("%Y-%m-%dT%H:%M"),
        "ends_at": timezone.localtime(schedule.ends_at).strftime("%Y-%m-%dT%H:%M"),
    }
    suggestion = student.get(reverse("recommendation"), dates)
    assert suggestion.status_code == 200 and suggestion.json()["recommended"]
    response = student.post(
        reverse("reserve"), dates | {"vehicle": vehicle.pk, "parking_lot": "", "purpose": "class"}
    )
    assert response.status_code == 302
    reservation = Reservation.objects.get(plate="FLOW123")
    assert response.url == reverse("reservation_detail", args=[reservation.code])
    assert student.get(response.url).status_code == 200
    qr_url = reverse("reservation_qr", args=[reservation.code])
    assert student.get(qr_url).status_code == 200
    officer = Client()
    officer.force_login(scenario["officer"])
    assert (
        len(
            officer.get(reverse("access"), {"search": str(reservation.code)}).context[
                "reservations"
            ]
        )
        == 1
    )
    with patch("parking.services.timezone.now", return_value=schedule.starts_at):
        assert officer.post(reverse("movement", args=[reservation.pk, "entry"])).status_code == 302
        assert student.get(reverse("availability")).json()["lots"][0]["occupied"] == 1
        assert officer.post(reverse("movement", args=[reservation.pk, "exit"])).status_code == 302
    assert student.get(qr_url).status_code == 410
    assert student.get(reverse("availability")).json()["lots"][0]["occupied"] == 0
    admin = Client()
    admin.force_login(manager)
    assert admin.get(reverse("reports"), {"plate": "FLOW123"}).context["total"] == 1
    assert b"FLOW123" in admin.get(reverse("report_csv"), {"plate": "FLOW123"}).content
    month = timezone.localtime(schedule.starts_at).strftime("%Y-%m")
    assert admin.get(reverse("indicators"), {"month": month}).context["summary"]["total"] == 1
    assert admin.get(reverse("audit")).status_code == 200
    assert AuditEvent.objects.filter(reservation=reservation).count() == 3
