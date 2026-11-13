"""Prueba opcional de desconexión real: pip install -r requirements-browser.txt."""

import os
import socket
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from time import monotonic, sleep
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix="parking-browser-") as directory:
        os.environ["PARKING_DATABASE_PATH"] = str(Path(directory) / "test.sqlite3")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django

        django.setup()
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group
        from django.core.management import call_command
        from django.utils import timezone
        from playwright.sync_api import expect, sync_playwright

        from parking.models import (
            AuditEvent,
            OfflineMovement,
            ParkingLot,
            Reservation,
            SecurityAssignment,
        )
        from parking.permissions import SECURITY_GROUP

        call_command("migrate", verbosity=0)
        officer = get_user_model().objects.create_user(
            "browser", email="browser@ulacit.ed.cr", password="BrowserTest2026!"
        )
        officer.groups.add(Group.objects.get_or_create(name=SECURITY_GROUP)[0])
        lot = ParkingLot.objects.create(name="Prueba", capacity=2)
        SecurityAssignment.objects.create(officer=officer, parking_lot=lot)
        now = timezone.now()
        row = Reservation.objects.create(
            user=officer,
            parking_lot=lot,
            plate="OFF123",
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(hours=1),
            entry_deadline=now + timedelta(minutes=10),
        )

        def database_state():
            def read():
                from django.db import connection

                result = {
                    "events": OfflineMovement.objects.count(),
                    "accepted": OfflineMovement.objects.filter(accepted=True).count(),
                    "status": Reservation.objects.get(pk=row.pk).status,
                    "entries": AuditEvent.objects.filter(reservation=row, action="entered").count(),
                    "exits": AuditEvent.objects.filter(reservation=row, action="exited").count(),
                }
                connection.close()
                return result

            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(read).result()

        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            deadline = monotonic() + 20
            while True:
                try:
                    urlopen(base + "/login/", timeout=1).close()
                    break
                except (URLError, TimeoutError):
                    if monotonic() > deadline:
                        raise RuntimeError("El servidor de prueba no inició.") from None
                    sleep(0.2)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context()
                page = context.new_page()
                page.goto(base + "/login/")
                page.locator('[name="username"]').fill(officer.email)
                page.locator('[name="password"]').fill("BrowserTest2026!")
                page.locator('button[type="submit"], button').last.click()
                page.wait_for_url(base + "/")
                page.goto(base + "/acceso/")
                page.evaluate("navigator.serviceWorker.ready")
                page.goto(base + "/acceso/dispositivo/")
                expect(page.get_by_role("button", name="Ingreso", exact=True)).to_be_visible()
                page.wait_for_function(
                    "document.getElementById('offline-state').textContent.includes('Conectado')"
                )
                context.set_offline(True)
                page.reload()
                page.get_by_role("button", name="Ingreso", exact=True).click()
                expect(page.locator("#offline-pending")).to_contain_text("Pendiente")
                page.reload()
                expect(page.locator("#offline-pending")).to_contain_text("OFF123")
                page.get_by_role("button", name="Salida", exact=True).click()
                expect(page.locator("#offline-pending li")).to_have_count(2)
                assert database_state()["events"] == 0
                context.set_offline(False)
                expect(page.locator("#offline-pending")).not_to_contain_text(
                    "Pendiente", timeout=20000
                )
                expect(page.locator("#offline-pending li")).to_have_count(2)
                assert database_state() == {
                    "events": 2,
                    "accepted": 2,
                    "status": "completed",
                    "entries": 1,
                    "exits": 1,
                }
                page.get_by_role("button", name="Sincronizar", exact=True).click()
                assert database_state()["events"] == 2
                # La consola normal también debe abrir la página local cuando no hay red.
                context.set_offline(True)
                page.goto(base + "/acceso/")
                expect(
                    page.get_by_role("heading", name="Movimientos del dispositivo")
                ).to_be_visible()
                browser.close()
            print(
                "OK: Chrome sin red, recarga, ingreso/salida persistentes, reconexión automática y sin duplicados."
            )
        finally:
            process.terminate()
            process.wait(timeout=10)
            from django.db import connection

            connection.close()


if __name__ == "__main__":
    main()
