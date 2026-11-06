from datetime import timedelta
from getpass import getpass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from parking.models import ClassSchedule, ParkingLot


class Command(BaseCommand):
    help = "Crea usuarios, tres parqueos y horarios de demostración sin borrar datos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", help="Contraseña local de demostración (mínimo 8 caracteres)."
        )

    def handle(self, *args, **options):
        password = options["password"] or getpass("Contraseña para los usuarios demo: ")
        if len(password) < 8:
            raise CommandError("Usa al menos 8 caracteres.")
        for name, capacity in [("Parqueo Norte", 12), ("Parqueo Central", 8), ("Parqueo Sur", 15)]:
            ParkingLot.objects.get_or_create(name=name, defaults={"capacity": capacity})
        for username, staff in [("estudiante", False), ("oficial", True)]:
            user, created = get_user_model().objects.get_or_create(
                username=username, defaults={"is_staff": staff}
            )
            if created:
                user.set_password(password)
                user.save()
            if not staff:
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
                "Demo lista: estudiante y oficial. Usuarios existentes conservan su contraseña."
            )
        )
