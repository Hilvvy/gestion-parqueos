from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from parking.forms import InstitutionalEmailField
from parking.models import ClassSchedule, Reservation
from parking.tests.test_integrated_flows import allow_reports
from parking.tests.test_parity import account_data, browser_data
from parking.tests.test_parity import manager as manager
from parking.tests.test_reservations import reserve


@pytest.mark.parametrize(
    "email", ["person@gmail.com", "person@ulacit.ed.cr.evil", "person@ulacit.ac.cr", "estudiante"]
)
def test_only_exact_institutional_domain_is_accepted(email):
    with pytest.raises(ValidationError):
        InstitutionalEmailField().clean(email)


def test_institutional_email_normalizes_case():
    assert (
        InstitutionalEmailField().clean(" SCHINCHILLAD502@ULACIT.ED.CR ")
        == "schinchillad502@ulacit.ed.cr"
    )


def test_login_rejects_username_even_with_correct_password(db):
    user = get_user_model().objects.create_user(
        "steven", email="schinchillad502@ulacit.ed.cr", password="DemoPassword2026!"
    )
    assert authenticate(username="steven", password="DemoPassword2026!") is None
    assert (
        authenticate(username="schinchillad502@ulacit.ed.cr", password="DemoPassword2026!") == user
    )


def test_user_creation_can_generate_identifier_from_email(client, manager):
    client.force_login(manager)
    data = browser_data(account_data())
    data.pop("username")
    response = client.post(reverse("manage_account_create"), data)
    assert response.status_code == 302
    assert get_user_model().objects.get(email=data["email"]).username == data["email"]


def test_admin_panel_and_sidebar_permissions(client, scenario, manager):
    client.force_login(scenario["user"])
    assert client.get(reverse("manage_dashboard")).status_code == 403
    page = client.get(reverse("dashboard")).content.decode()
    assert 'id="app-sidebar"' in page and 'class="app-bar"' not in page
    assert reverse("manage_dashboard") not in page
    client.force_login(manager)
    page = client.get(reverse("manage_dashboard"))
    assert page.status_code == 200 and b"Crear usuario" in page.content


def test_login_keeps_sidebar_hidden(client):
    page = client.get(reverse("login")).content.decode()
    assert 'id="app-sidebar"' not in page
    assert "Correo institucional" in page


@pytest.mark.parametrize("seconds,accepted", [(0, True), (1, False)])
def test_reservation_window_exactly_48_hours(scenario, seconds, accepted):
    now = scenario["starts_at"] - timedelta(days=1)
    start = now + timedelta(hours=48, seconds=seconds)
    end = start + timedelta(hours=1)
    ClassSchedule.objects.create(
        user=scenario["user"], course="Límite", starts_at=start, ends_at=end
    )
    with patch("parking.booking_rules.timezone.now", return_value=now):
        if accepted:
            assert reserve(scenario, starts_at=start, ends_at=end).pk
        else:
            with pytest.raises(ValidationError, match="48 horas"):
                reserve(scenario, starts_at=start, ends_at=end)
    assert Reservation.objects.count() == int(accepted)


def test_recommendation_rejects_more_than_48_hours(client, scenario):
    client.force_login(scenario["user"])
    start = timezone.now() + timedelta(hours=49)
    response = client.get(
        reverse("recommendation"),
        {
            "starts_at": timezone.localtime(start).strftime("%Y-%m-%dT%H:%M"),
            "ends_at": timezone.localtime(start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        },
    )
    assert response.status_code == 400


def test_excel_export_filters_native_dates_and_private_response(client, scenario):
    reservation = reserve(scenario)
    Reservation.objects.create(
        user=scenario["user"],
        parking_lot=scenario["parking_lot"],
        plate="OTHER123",
        starts_at=scenario["starts_at"] + timedelta(days=2),
        ends_at=scenario["ends_at"] + timedelta(days=2),
    )
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    response = client.get(reverse("report_excel"), {"plate": "ABC"})
    assert response.status_code == 200
    assert (
        response["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert (
        "no-store" in response["Cache-Control"]
        and "reservas.xlsx" in response["Content-Disposition"]
    )
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook["Reservas"]
    assert sheet.max_row == 6 and sheet["B6"].value == "ABC123"
    assert sheet["F6"].value == timezone.localtime(reservation.starts_at).replace(
        tzinfo=None, microsecond=0
    )
    assert sheet["F6"].is_date
    assert sheet.freeze_panes == "C6"
    assert "Reservas" in sheet.tables
    workbook.close()


def test_excel_uses_text_for_formula_like_user_values(client, scenario):
    scenario["parking_lot"].name = "=1+1"
    scenario["parking_lot"].save()
    reserve(scenario)
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    workbook = load_workbook(BytesIO(client.get(reverse("report_excel")).content))
    cell = workbook["Reservas"]["D6"]
    assert cell.value == "=1+1" and cell.data_type == "s"
    workbook.close()


def test_excel_empty_results_and_invalid_filters(client, scenario):
    allow_reports(scenario["officer"])
    client.force_login(scenario["officer"])
    response = client.get(reverse("report_excel"))
    workbook = load_workbook(BytesIO(response.content))
    assert workbook["Reservas"].max_row == 5
    workbook.close()
    assert (
        client.get(
            reverse("report_excel"), {"date_from": "2030-02-01", "date_to": "2030-01-01"}
        ).status_code
        == 400
    )


def test_excel_does_not_allow_student_access(client, scenario):
    client.force_login(scenario["user"])
    assert client.get(reverse("report_excel")).status_code == 403
