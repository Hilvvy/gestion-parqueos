import time

from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections

from parking.services import ReservationService


class Command(BaseCommand):
    help = (
        "Vence citas sin ingreso; --watch procesa periódicamente sin depender de páginas abiertas."
    )

    def add_arguments(self, parser):
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=15)

    def handle(self, *args, **options):
        if options["interval"] < 1:
            raise CommandError("El intervalo debe ser de al menos un segundo.")
        try:
            while True:
                try:
                    count = ReservationService.expire_no_shows()
                    if count or not options["watch"]:
                        self.stdout.write(f"Citas vencidas: {count}")
                except OperationalError:
                    if not options["watch"]:
                        raise
                    self.stderr.write("Base ocupada; se reintentará en el siguiente ciclo.")
                finally:
                    close_old_connections()
                if not options["watch"]:
                    break
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Procesador detenido.")
