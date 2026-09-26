#!/usr/bin/env python3
"""Create the deliberately messy demo folder `sample_inbox/` (fictional data only)."""
from __future__ import annotations

import csv
import os
import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
INBOX = HERE / "sample_inbox"


def main() -> None:
    if INBOX.exists():
        shutil.rmtree(INBOX)
    INBOX.mkdir()

    # 1. Clean-ish January CSV (comma, ISO dates, one blank line, stray spaces)
    jan = [
        ["Order ID", "Date", "Customer", "Region", "Product", "Qty", "Amount"],
        ["A-1001", "2026-01-05", "Northwind Ltd", "North", "Starter plan", "1", "49.00"],
        ["A-1002", "2026-01-07", "Blue Harbor Co", "south ", "Team plan", "3", "447.00"],
        ["A-1003", "2026-01-09", "Kestrel Foods", "East", "Starter plan", "2", "98.00"],
        ["A-1004", "2026-01-12", " Orchid Studio", "West", "Pro plan", "1", "199.00"],
        [],
        ["A-1005", "2026-01-15", "Northwind Ltd", "North", "Add-on seats", "10", "150.00"],
        ["A-1006", "2026-01-20", "Maple & Stone", "south", "Team plan", "2", "298.00"],
        ["A-1007", "2026-01-28", "Kestrel Foods", "East", "Pro plan", "1", "199.00"],
    ]
    with (INBOX / "Sales Jan 2026.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(jan)

    # 2. February CSV from a European system: semicolons, dd/mm/yyyy, 1.234,50 decimals,
    #    cp1252 encoding, different header names, one missing amount, one impossible date.
    feb = [
        ["Order No", "Order Date", "Client", "Area", "Item", "Units", "Total"],
        ["A-1008", "02/02/2026", "Café Lumière", "West", "Team plan", "4", "596,00"],
        ["A-1009", "05/02/2026", "Blue Harbor Co", "South", "Pro plan", "10", "1.990,00"],
        ["A-1010", "11/02/2026", "Orchid Studio", "WEST", "Add-on seats", "5", "75,00"],
        ["A-1011", "14/02/2026", "Northwind Ltd", "North", "Pro plan", "2", ""],
        ["A-1012", "31/02/2026", "Kestrel Foods", "East", "Starter plan", "1", "49,00"],
        ["A-1013", "26/02/2026", "Maple & Stone", "South", "Pro plan", "1", "199,00"],
    ]
    with (INBOX / "sales_feb-2026 FINAL (2).csv").open("w", newline="", encoding="cp1252") as fh:
        csv.writer(fh, delimiter=";").writerows(feb)

    # 3. March Excel export: title rows above the header, real dates, "$1,250.00" text
    #    amounts, trailing spaces, and two orders that were already in January.
    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    ws.append(["ACME billing export"])
    ws.append(["Generated 2026-04-01 by billing system"])
    ws.append([])
    ws.append(["order #", "orderdate", "Company", "Territory", "SKU", "qty", "Revenue"])
    march = [
        ["A-1014", datetime(2026, 3, 2), "Northwind Ltd", "North ", "Team plan", 5, "$745.00"],
        ["A-1015", datetime(2026, 3, 4), "Blue Harbor Co", "South", "Add-on seats", 20, "$300.00"],
        ["A-1003", datetime(2026, 1, 9), "Kestrel Foods", "East", "Starter plan", 2, "$98.00"],
        ["A-1016", datetime(2026, 3, 9), "Café Lumière", "west", "Pro plan", 3, "$597.00"],
        ["A-1017", datetime(2026, 3, 16), "Orchid Studio", "West", "Enterprise plan", 1, "$1,250.00"],
        [None, None, None, None, None, None, None],
        ["A-1006", datetime(2026, 1, 20), "Maple & Stone", "South", "Team plan", 2, "$298.00"],
        ["A-1018", datetime(2026, 3, 23), "Kestrel Foods", "East", "Team plan", 3, "$447.00"],
        ["A-1019", datetime(2026, 3, 30), "Maple & Stone", "south", "Enterprise plan", 1, "$1,250.00"],
    ]
    for row in march:
        ws.append(row)
    march_path = INBOX / "March export.xlsx"
    wb.save(march_path)

    # 4. A byte-identical copy (should land in Duplicates, not be merged twice)
    shutil.copy2(march_path, INBOX / "Copy of March export.xlsx")
    # 5. Excel's temporary lock file (must be ignored)
    (INBOX / "~$March export.xlsx").write_bytes(b"\x00lock")

    # 6. Other clutter that needs sorting
    try:
        from reportlab.pdfgen import canvas  # noqa: PLC0415

        pdf = canvas.Canvas(str(INBOX / "Invoice #443 (copy).pdf"))
        pdf.drawString(72, 750, "Invoice #443 - demo document")
        pdf.save()
    except ImportError:
        (INBOX / "Invoice #443 (copy).pdf").write_bytes(b"%PDF-1.4\n% demo invoice placeholder\n%%EOF\n")
    try:
        from PIL import Image  # noqa: PLC0415

        Image.new("RGB", (64, 48), (250, 204, 21)).save(INBOX / "IMG_2041.JPG", "JPEG")
    except ImportError:
        (INBOX / "IMG_2041.JPG").write_bytes(b"\xff\xd8\xff\xd9")
    (INBOX / "meeting notes.txt").write_text("Q1 review: merge the monthly exports into one report.\n", encoding="utf-8")
    (INBOX / "backup.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # empty zip archive
    (INBOX / "data dump.xyz").write_text("unknown format\n", encoding="utf-8")
    # Realistic "last modified" dates (the organizer uses them in new file names)
    stamps = {"Sales Jan 2026.csv": "2026-02-02", "sales_feb-2026 FINAL (2).csv": "2026-03-03",
              "March export.xlsx": "2026-04-01", "Copy of March export.xlsx": "2026-04-06",
              "Invoice #443 (copy).pdf": "2026-03-18", "IMG_2041.JPG": "2026-03-21",
              "meeting notes.txt": "2026-04-02", "backup.zip": "2026-01-30", "data dump.xyz": "2026-02-14"}
    for name, day in stamps.items():
        ts = datetime.fromisoformat(day + "T09:30:00").timestamp()
        os.utime(INBOX / name, (ts, ts))
    print(f"Created {len(list(INBOX.iterdir()))} files in {INBOX}")


if __name__ == "__main__":
    main()
