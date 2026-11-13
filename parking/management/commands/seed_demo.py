from datetime import timedelta
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from parking.models import (
    ClassSchedule,
    ParkingLot,
    ParkingPolicy,
    SecurityAssignment,
    UserProfile,
    Vehicle,
)
from parking.permissions import configure_roles


class Command(BaseCommand):
    help = "Carga cuentas, parqueos, vehículo y horarios demo sin borrar datos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", help="Contraseña para las cuentas nuevas (mínimo 8 caracteres)."
        )

    def handle(self, *args, **options):
        password = options["password"] or getpass("Contraseña para las cuentas nuevas: ")
        if len(password) < 8:
            raise CommandError("Usa al menos 8 caracteres.")
        lots = []
        for name, capacity in [("Parqueo Norte", 12), ("Parqueo Central", 8), ("Parqueo Sur", 15)]:
            lot, _ = ParkingLot.objects.get_or_create(name=name, defaults={"capacity": capacity})
            lots.append(lot)
        ParkingPolicy.objects.get_or_create(pk=1)
        security, administrators = configure_roles()
        for username in ("estudiante", "oficial", "administrador"):
            user, created = get_user_model().objects.get_or_create(
                username=username,
                defaults={
                    "is_staff": username == "administrador",
                    "is_superuser": username == "administrador",
                },
            )
            if created:
                user.set_password(password)
                user.save()
            if not user.email:
                user.email = f"{username}@parqueos.example"
                user.save(update_fields=["email"])
            profile, _ = UserProfile.objects.get_or_create(user=user)
            if not profile.career and username == "estudiante":
                profile.career = "Ingeniería Informática"
            if username == "oficial" and not profile.shift:
                from datetime import time

                profile.shift = UserProfile.Shift.MIXED
                profile.work_start = time(14, 0)
                profile.work_end = time(22, 0)
            profile.save()
            if username == "oficial":
                user.groups.add(security)
                for lot in lots:
                    SecurityAssignment.objects.get_or_create(officer=user, parking_lot=lot)
            elif username == "administrador":
                user.groups.add(administrators)
            else:
                if (
                    not Vehicle.objects.filter(owner=user, active=True).exists()
                    and not Vehicle.objects.filter(plate="DEMO123", active=True).exists()
                ):
                    Vehicle.objects.create(
                        owner=user,
                        plate="DEMO123",
                        kind=Vehicle.Kind.CAR,
                        brand="Toyota",
                        model="Corolla",
                    )
                for offset in range(7):
                    start = timezone.localtime().replace(
                        hour=7, minute=0, second=0, microsecond=0
                    ) + timedelta(days=offset)
                    ClassSchedule.objects.get_or_create(
                        user=user,
                        course="Taller de proyecto · demostración",
                        starts_at=start,
                        ends_at=start.replace(hour=22),
                    )
        self.stdout.write(
            self.style.SUCCESS(
                "Demo lista: estudiante, oficial y administrador. Se conservan las contraseñas existentes."
            )
        )
