from io import BytesIO
from math import ceil

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


def reservation_workbook(reservations, filters):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Reservas"
    sheet.sheet_view.showGridLines = False
    sheet.merge_cells("A1:L1")
    sheet["A1"] = "Historial de reservas y accesos"
    sheet["A1"].font = Font(name="Calibri", size=18, bold=True, color="6D28A8")
    sheet.row_dimensions[1].height = 30
    sheet.merge_cells("A2:L2")
    sheet["A2"] = (
        f"Parqueos ULACIT · Generado {timezone.localtime():%d/%m/%Y %H:%M} · Horas de Costa Rica"
    )
    description = (
        " · ".join(
            f"{label}: {filters[key]}"
            for key, label in [
                ("plate", "Placa"),
                ("date_from", "Desde"),
                ("date_to", "Hasta"),
                ("status", "Estado"),
            ]
            if filters.get(key)
        )
        or "Todas las reservas"
    )
    sheet.merge_cells("A3:L3")
    sheet["A3"] = description
    sheet["A3"].data_type = "s"
    headers = [
        "Código",
        "Placa",
        "Correo",
        "Parqueo",
        "Motivo",
        "Inicio",
        "Fin",
        "Estado",
        "Ingreso",
        "Oficial ingreso",
        "Salida",
        "Oficial salida",
    ]
    sheet.append([])
    for column, header in enumerate(headers, 1):
        cell = sheet.cell(5, column, header)
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="6D28A8")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    sheet.row_dimensions[5].height = 28

    def local_date(value):
        return timezone.localtime(value).replace(tzinfo=None) if value else None

    widths = [39, 15, 38, 24, 22, 22, 22, 18, 22, 38, 22, 38]
    for index, row in enumerate(reservations.iterator(), 6):
        values = [
            str(row.code),
            row.plate,
            row.user.email,
            row.parking_lot.name,
            row.get_purpose_display(),
            local_date(row.starts_at),
            local_date(row.ends_at),
            row.get_status_display(),
            local_date(row.entered_at),
            row.officer.email if row.officer else "",
            local_date(row.exited_at),
            row.exit_officer.email if row.exit_officer else "",
        ]
        for column, value in enumerate(values, 1):
            cell = sheet.cell(index, column)
            if isinstance(value, str):
                cell.value = ILLEGAL_CHARACTERS_RE.sub("", value)
                cell.data_type = "s"
            else:
                cell.value = value
            cell.font = Font(name="Calibri", size=11, color="202124")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            if column in (6, 7, 9, 11):
                cell.number_format = "dd/mm/yyyy hh:mm"
        sheet.row_dimensions[index].height = max(
            22,
            14
            * max(
                (
                    ceil(len(value) / (widths[column] - 2))
                    for column, value in enumerate(values)
                    if isinstance(value, str)
                ),
                default=1,
            ),
        )
    if sheet.max_row >= 6:
        table = Table(displayName="Reservas", ref=f"A5:L{sheet.max_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium4", showRowStripes=True)
        sheet.add_table(table)
    else:
        sheet.auto_filter.ref = "A5:L5"
    for column, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(column)].width = width
    sheet.freeze_panes = "C6"
    sheet.print_title_rows = "1:5"
    sheet.page_setup.orientation = "landscape"
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
