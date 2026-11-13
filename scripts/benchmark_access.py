"""Medición reproducible con base temporal; no toca los datos de la demo."""

import json
import os
import platform
import sys
import tempfile
from datetime import timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="parking-benchmark-") as directory:
        os.environ["PARKING_DATABASE_PATH"] = str(Path(directory) / "benchmark.sqlite3")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django

        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.test import Client
        from django.utils import timezone

        from parking.models import ParkingLot, Reservation

        call_command("migrate", verbosity=0)
        user = get_user_model().objects.create_user("benchmark", is_superuser=True)
        lot = ParkingLot.objects.create(name="Benchmark", capacity=10000)
        now = timezone.now()
        Reservation.objects.bulk_create(
            [
                Reservation(
                    user=user,
                    parking_lot=lot,
                    plate=f"P{i:06}",
                    starts_at=now - timedelta(days=7),
                    ends_at=now - timedelta(days=6),
                    status="completed",
                )
                for i in range(10000)
            ]
        )
        client = Client()
        client.force_login(user)
        client.get("/reportes/")
        timings = {"historial_filtrado": [], "buscar_y_validar_ingreso": []}
        for index in range(30):
            start = perf_counter()
            response = client.get(
                "/reportes/",
                {
                    "plate": "P000",
                    "date_from": (now - timedelta(days=8)).date().isoformat(),
                    "date_to": now.date().isoformat(),
                },
            )
            assert response.status_code == 200
            timings["historial_filtrado"].append(perf_counter() - start)
            row = Reservation.objects.create(
                user=user,
                parking_lot=lot,
                plate=f"V{index:05}",
                starts_at=now - timedelta(minutes=1),
                ends_at=now + timedelta(hours=1),
                entry_deadline=now + timedelta(minutes=10),
            )
            start = perf_counter()
            assert client.get("/acceso/", {"search": row.plate}).status_code == 200
            assert client.post(f"/acceso/{row.pk}/entry/").status_code == 302
            row.refresh_from_db()
            assert row.status == "inside"
            timings["buscar_y_validar_ingreso"].append(perf_counter() - start)
        result = {
            "environment": f"{platform.system()} {platform.machine()} / Python {platform.python_version()} / Django {django.get_version()} / SQLite",
            "records": 10000,
            "samples": 30,
            "transport": "Django Client local; sin red ni navegador",
            "seconds": {
                name: {
                    "median": round(median(values), 4),
                    "p95": round(sorted(values)[28], 4),
                    "max": round(max(values), 4),
                }
                for name, values in timings.items()
            },
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        from django.db import connection

        connection.close()


if __name__ == "__main__":
    main()
