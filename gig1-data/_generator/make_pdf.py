"""Generate a 5-page text-based PDF: a 3-page business bank statement + 2 supplier invoices.

Everything is fictional (bank, business, suppliers, account number). One invoice contains a
deliberate arithmetic error (3 x 48.50 printed as 154.50) so the reconciliation has something
real to catch. Run: python make_pdf.py
"""
import datetime as dt
import os
import random
from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "02-pdf-statement-invoices", "before_statement_and_invoices.pdf")
R = random.Random(41)
NAVY, GREY, LIGHT, RULE = HexColor("#1F2A44"), HexColor("#6B7280"), HexColor("#F3F4F6"), HexColor("#D1D5DB")
W, H = letter
FOOT = "Fictional sample document created for portfolio use. Not a real bank, business or account."


def q(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def m(v):
    return f"{v:,.2f}"


# ------------------------------------------------------------------ data
INV1 = {"vendor": "Greenleaf Produce Supply", "tag": "Wholesale produce and dairy", "no": "INV-2041",
        "date": "April 6, 2026", "due": "April 20, 2026",
        "lines": [("Organic strawberries (flat)", 6, "38.00", "228.00"),
                  ("Lemons (case, 115 ct)", 4, "42.75", "171.00"),
                  ("Free-range eggs (15 dozen case)", 5, "54.20", "271.00"),
                  ("Unsalted butter (36 lb case)", 3, "48.50", "154.50"),   # deliberate error: should be 145.50
                  ("Heavy cream (gallon)", 12, "11.90", "142.80"),
                  ("Fresh mint (bunch)", 10, "2.25", "22.50")],
        "tax_label": "Sales tax (exempt)", "tax_rate": None}
INV2 = {"vendor": "Mill & Crumb Flour Co.", "tag": "Flour, sugar and baking supplies", "no": "INV-88317",
        "date": "April 13, 2026", "due": "May 13, 2026",
        "lines": [("Bread flour, 50 lb bag", 12, "31.40", None), ("Whole wheat flour, 50 lb bag", 4, "34.10", None),
                  ("Rye flour, 25 lb bag", 3, "22.65", None), ("Cane sugar, 50 lb bag", 5, "41.80", None),
                  ("Instant yeast, 1 lb", 10, "6.35", None), ("Sea salt, 25 lb", 2, "18.90", None),
                  ("Delivery fee", 1, "25.00", None)],
        "tax_label": "Sales tax (6%)", "tax_rate": Decimal("0.06")}
for inv in (INV1, INV2):
    lines = []
    for d, qty, unit, amt in inv["lines"]:
        amt = Decimal(amt) if amt else q(Decimal(unit) * qty)
        lines.append((d, qty, Decimal(unit), amt))
    inv["lines"] = lines
    inv["subtotal"] = sum((x[3] for x in lines), Decimal(0))
    inv["tax"] = q(inv["subtotal"] * inv["tax_rate"]) if inv["tax_rate"] else Decimal("0.00")
    inv["total"] = inv["subtotal"] + inv["tax"]


def transactions():
    """Build April 2026 activity for a small bakery. Returns list of (date, desc, desc2, debit, credit)."""
    tx = []
    for day in range(1, 31):
        d = dt.date(2026, 4, day)
        if d.weekday() < 6:  # card settlements Mon-Sat
            tx.append((d, f"CARD SALES DEPOSIT BATCH {d:%m%d}", None, None, q(R.uniform(610, 1480))))
        if d.weekday() == 0:
            tx.append((d, "CASH DEPOSIT BRANCH 014", None, None, q(R.uniform(240, 520))))
    fixed = [
        (1, "RENT - LARKSPUR PROPERTIES LLC", "APRIL LEASE UNIT 2", Decimal("3850.00"), None),
        (3, "PAYROLL - STAFF NET PAY", "PERIOD 03/16-03/31", Decimal("6912.44"), None),
        (6, "CARD PURCHASE HARBOR SUPPLY WHSE", None, Decimal("412.87"), None),
        (8, "LAKESHORE ELECTRIC CO-OP", "ACCT ENDING 7720", Decimal("688.15"), None),
        (9, "CATERING PAYMENT RECEIVED", "OAK HOLLOW INN EVENT 04/04", None, Decimal("1860.00")),
        (10, "CITY WATER UTILITY", None, Decimal("143.60"), None),
        (13, "ASHGROVE MUTUAL INSURANCE", "POLICY BOP-55120", Decimal("326.40"), None),
        (15, "MERCHANT SERVICE FEE", "MARCH PROCESSING", Decimal("284.19"), None),
        (16, "ONLINE ORDER PAYOUT", "PICKUP ORDERS 04/01-04/15", None, Decimal("2144.37")),
        (17, f"ACH PAYMENT GREENLEAF PRODUCE {INV1['no']}", None, INV1["total"], None),
        (17, "PAYROLL - STAFF NET PAY", "PERIOD 04/01-04/15", Decimal("7045.10"), None),
        (20, "STATE SALES TAX PAYMENT", "MARCH RETURN", Decimal("1937.26"), None),
        (22, "CARD PURCHASE HARBOR SUPPLY WHSE", None, Decimal("256.30"), None),
        (23, "EQUIPMENT LEASE - OVENWORKS FINANCE", "CONTRACT 3391", Decimal("515.00"), None),
        (24, "CATERING PAYMENT RECEIVED", "RIVERBEND MARKET 04/18", None, Decimal("940.00")),
        (27, "ACH MILL AND CRUMB FLOUR CO", None, INV2["total"], None),
        (28, "WASTE HAULING - CLEARBIN SERVICES", None, Decimal("189.00"), None),
        (29, "ONLINE ORDER PAYOUT", "PICKUP ORDERS 04/16-04/29", None, Decimal("2388.52")),
        (30, "MONTHLY SERVICE FEE", None, Decimal("25.00"), None),
    ]
    small = ["CARD PURCHASE MAPLE HOLLOW DAIRY", "CARD PURCHASE CITY PACKAGING", "CARD PURCHASE HARBOR SUPPLY WHSE",
             "CARD PURCHASE NORTHSHORE HARDWARE", "CARD PURCHASE BAYSIDE OFFICE"]
    for day in (2, 4, 7, 11, 14, 18, 21, 25, 26, 29):
        fixed.append((day, R.choice(small), None, q(R.uniform(18, 240)), None))
    for day, desc, desc2, deb, cred in fixed:
        tx.append((dt.date(2026, 4, day), desc, desc2, deb, cred))
    tx.sort(key=lambda t: (t[0], t[4] is None))  # credits first on the same day
    return tx


OPENING = Decimal("18452.37")
FIRST_ROW_Y = H - 100 - 80 - 22 - 18 - 15   # page 1: below summary, table header, opening row
NEXT_ROW_Y = H - 100 - 18 - 15              # later pages: below table header and balance-forward row


# ------------------------------------------------------------------ drawing helpers
def page_frame(c, page, total, title):
    c.setFillColor(NAVY)
    c.rect(0, H - 70, W, 70, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, H - 42, "Harborline Community Bank")
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 50, H - 36, title)
    c.drawRightString(W - 50, H - 50, f"Page {page} of {total}")
    c.setFillColor(GREY)
    c.setFont("Helvetica", 7.5)
    c.drawString(50, 30, FOOT)
    c.setFillColor(HexColor("#111827"))


COLS = {"date": 50, "desc": 100, "wd": 420, "dep": 492, "bal": 562}


def table_header(c, y):
    c.setFillColor(LIGHT)
    c.rect(44, y - 5, W - 88, 17, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(COLS["date"], y, "Date")
    c.drawString(COLS["desc"], y, "Description")
    c.drawRightString(COLS["wd"], y, "Withdrawals")
    c.drawRightString(COLS["dep"], y, "Deposits")
    c.drawRightString(COLS["bal"], y, "Balance")
    c.setFillColor(HexColor("#111827"))
    c.setFont("Helvetica", 9)
    return y - 18


def make_statement(c):
    tx = transactions()
    credits = sum((t[4] for t in tx if t[4]), Decimal(0))
    debits = sum((t[3] for t in tx if t[3]), Decimal(0))
    closing = OPENING + credits - debits
    n_cr = sum(1 for t in tx if t[4])
    n_db = sum(1 for t in tx if t[3])
    # pass 1: paginate by height (row 15pt, +11pt when there is a second description line)
    pages, cur = [], []
    y, bottom = FIRST_ROW_Y, 70
    for t in tx:
        h = 15 + (11 if t[2] else 0)
        if y - h < bottom:
            pages.append(cur)
            cur, y = [], NEXT_ROW_Y
        cur.append(t)
        y -= h
    if y - 36 < bottom:  # room for closing balance + totals lines
        pages.append(cur)
        cur = []
    pages.append(cur)
    total_pages = len(pages)
    bal = OPENING
    for pno, rows in enumerate(pages, 1):
        page_frame(c, pno, total_pages, "Business Checking Statement")
        y = H - 100
        if pno == 1:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Bluebird Bakery & Cafe LLC")
            c.setFont("Helvetica", 9)
            c.drawString(50, y - 13, "Business Checking  •  Account ****4821")
            c.drawString(50, y - 26, "Statement period: April 1, 2026 to April 30, 2026")
            # summary box
            bx, by = 330, y + 12
            c.setStrokeColor(RULE)
            c.setFillColor(LIGHT)
            c.roundRect(bx, by - 78, 232, 84, 4, stroke=1, fill=1)
            c.setFillColor(NAVY)
            c.setFont("Helvetica-Bold", 9)
            c.drawString(bx + 10, by - 10, "Account summary")
            c.setFillColor(HexColor("#111827"))
            c.setFont("Helvetica", 8.5)
            items = [("Opening balance on April 1, 2026", OPENING),
                     (f"Deposits and other credits ({n_cr})", credits),
                     (f"Withdrawals and other debits ({n_db})", debits),
                     ("Closing balance on April 30, 2026", closing)]
            for k, (lab, val) in enumerate(items):
                yy = by - 26 - 13 * k
                if k == 3:
                    c.setFont("Helvetica-Bold", 8.5)
                c.drawString(bx + 10, yy, lab)
                c.drawRightString(bx + 222, yy, "$" + m(val))
            y -= 80
            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(NAVY)
            c.drawString(50, y, "Account activity")
            c.setFillColor(HexColor("#111827"))
            y -= 22
        y = table_header(c, y)
        if pno == 1:
            c.drawString(COLS["desc"], y, "Opening balance")
            c.drawRightString(COLS["bal"], y, m(OPENING))
        else:
            c.setFillColor(GREY)
            c.drawString(COLS["desc"], y, "Balance forward")
            c.drawRightString(COLS["bal"], y, m(bal))
            c.setFillColor(HexColor("#111827"))
        y -= 15
        for d, desc, desc2, deb, cred in rows:
            bal = bal + (cred or 0) - (deb or 0)
            c.drawString(COLS["date"], y, d.strftime("%m/%d"))
            c.drawString(COLS["desc"], y, desc)
            if deb:
                c.drawRightString(COLS["wd"], y, m(deb))
            if cred:
                c.drawRightString(COLS["dep"], y, m(cred))
            c.drawRightString(COLS["bal"], y, m(bal))
            if desc2:
                y -= 11
                c.setFillColor(GREY)
                c.setFont("Helvetica", 8)
                c.drawString(COLS["desc"], y, desc2)
                c.setFont("Helvetica", 9)
                c.setFillColor(HexColor("#111827"))
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.line(44, y - 4, W - 44, y - 4)
            y -= 15
        if pno == total_pages:
            y -= 4
            c.setFont("Helvetica-Bold", 9)
            c.drawString(COLS["desc"], y, "Closing balance")
            c.drawRightString(COLS["bal"], y, m(bal))
            y -= 14
            c.drawString(COLS["desc"], y, "Totals")
            c.drawRightString(COLS["wd"], y, m(debits))
            c.drawRightString(COLS["dep"], y, m(credits))
            c.setFont("Helvetica", 9)
        c.showPage()
    assert bal == closing
    return {"opening": OPENING, "closing": closing, "credits": credits, "debits": debits, "n": len(tx),
            "pages": total_pages}


def make_invoice(c, inv):
    c.setFillColor(HexColor("#FFFFFF"))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, H - 70, inv["vendor"])
    c.setFont("Helvetica", 9)
    c.setFillColor(GREY)
    c.drawString(50, H - 86, inv["tag"])
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(W - 50, H - 72, "INVOICE")
    c.setFillColor(HexColor("#111827"))
    c.setFont("Helvetica", 10)
    y = H - 130
    c.drawString(50, y, f"Invoice No: {inv['no']}")
    c.drawString(50, y - 15, f"Invoice Date: {inv['date']}")
    c.drawString(50, y - 30, f"Due Date: {inv['due']}")
    c.drawString(330, y, "Bill to: Bluebird Bakery & Cafe LLC")
    c.drawString(330, y - 15, "Terms: Net 14 days" if inv["no"] == "INV-2041" else "Terms: Net 30 days")
    y -= 75
    c.setFillColor(NAVY)
    c.rect(44, y - 6, W - 88, 20, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(52, y, "Description")
    c.drawRightString(370, y, "Qty")
    c.drawRightString(460, y, "Unit Price")
    c.drawRightString(560, y, "Amount")
    c.setFillColor(HexColor("#111827"))
    c.setFont("Helvetica", 10)
    y -= 24
    for k, (d, qty, unit, amt) in enumerate(inv["lines"]):
        if k % 2:
            c.setFillColor(LIGHT)
            c.rect(44, y - 5, W - 88, 18, stroke=0, fill=1)
            c.setFillColor(HexColor("#111827"))
        c.drawString(52, y, d)
        c.drawRightString(370, y, str(qty))
        c.drawRightString(460, y, m(unit))
        c.drawRightString(560, y, m(amt))
        y -= 18
    y -= 16
    c.setStrokeColor(RULE)
    c.line(360, y + 12, W - 44, y + 12)
    for lab, val, bold in [("Subtotal", inv["subtotal"], False), (inv["tax_label"], inv["tax"], False),
                           ("Total due", inv["total"], True)]:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawString(380, y, lab)
        c.drawRightString(560, y, ("$" if bold else "") + m(val))
        y -= 17
    c.setFont("Helvetica", 9)
    c.setFillColor(GREY)
    c.drawString(50, 90, "Payment by ACH within terms. Please reference the invoice number with your payment.")
    c.drawString(50, 30, FOOT)
    c.showPage()


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    c = canvas.Canvas(OUT, pagesize=letter)
    c.setTitle("Sample bank statement and invoices (fictional)")
    c.setAuthor("Sample data")
    st = make_statement(c)
    make_invoice(c, INV1)
    make_invoice(c, INV2)
    c.save()
    print(f"wrote {OUT}")
    print(f"statement: {st['pages']} pages, {st['n']} transactions, opening {st['opening']}, credits {st['credits']}, debits {st['debits']}, closing {st['closing']}")
    for inv in (INV1, INV2):
        print(f"{inv['no']}: subtotal {inv['subtotal']} tax {inv['tax']} total {inv['total']}")


if __name__ == "__main__":
    main()
