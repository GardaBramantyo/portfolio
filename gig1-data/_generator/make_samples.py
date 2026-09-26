"""Generate the three messy "before" files for the Gig 1 portfolio (deterministic, seed 2026).

All people, companies, banks, emails and phone numbers are FICTIONAL:
- emails use the reserved example.com / example.net / example.org domains
- US/Canada phones use the reserved 555-0100..555-0199 fictional range
- UK phones use Ofcom's drama range 07700 900000..900999
Run from anywhere: python make_samples.py
"""
import csv
import datetime as dt
import os
import random
from decimal import ROUND_HALF_UP, Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R = random.Random(2026)

FIRST = ["James", "Olivia", "Liam", "Emma", "Noah", "Ava", "Elijah", "Sophia", "Lucas", "Mia", "Mason",
         "Amelia", "Ethan", "Harper", "Logan", "Evelyn", "Aiden", "Abigail", "Carter", "Ella", "Owen",
         "Scarlett", "Wyatt", "Grace", "Caleb", "Chloe", "Isaac", "Lily", "Julian", "Aria", "Levi",
         "Nora", "Hunter", "Zoe", "Dylan", "Hannah", "Nathan", "Layla", "Adrian", "Riley", "Priya",
         "Arjun", "Mei", "Wei", "Diego", "Sofia", "Mateo", "Camila", "Omar", "Leila", "Tomas", "Ingrid",
         "Kofi", "Amara", "Hiro", "Yuki", "Rafael", "Lucia", "Aisha", "Tariq", "Nadia", "Felix", "Clara",
         "Marcus", "Talia", "Declan", "Maeve", "Rowan", "Freya", "Silas", "Iris"]
LAST = ["Anderson", "Brooks", "Carter", "Dawson", "Ellis", "Fleming", "Garner", "Hayes", "Ingram",
        "Jennings", "Keller", "Lawson", "Mercer", "Nolan", "Osborne", "Pruitt", "Quinn", "Ramsey",
        "Sutton", "Thornton", "Underwood", "Vaughn", "Whitaker", "Yates", "Abbott", "Barlow", "Conley",
        "Delgado", "Estrada", "Fischer", "Gallagher", "Hartman", "Iverson", "Jarvis", "Kemp", "Lindgren",
        "Maddox", "Nakamura", "Okafor", "Patel", "Reyes", "Sandoval", "Tanaka", "Vasquez", "Webb",
        "Zimmerman", "O'Connell", "McAllister", "Van Buren", "Ashford", "Blackwood", "Callahan",
        "Donovan", "Everett", "Fairbanks", "Holloway", "Kowalski", "Montoya", "Pemberton", "Rhodes"]
US = [("Austin", "TX", "78701", "512"), ("Dallas", "TX", "75201", "214"), ("Houston", "TX", "77002", "713"),
      ("Boston", "MA", "02108", "617"), ("Cambridge", "MA", "02139", "617"), ("Hartford", "CT", "06103", "860"),
      ("Newark", "NJ", "07102", "973"), ("Portland", "OR", "97201", "503"), ("Seattle", "WA", "98101", "206"),
      ("Denver", "CO", "80202", "303"), ("Phoenix", "AZ", "85004", "602"), ("Chicago", "IL", "60601", "312"),
      ("Columbus", "OH", "43215", "614"), ("Atlanta", "GA", "30303", "404"), ("Miami", "FL", "33130", "305"),
      ("Nashville", "TN", "37203", "615"), ("Minneapolis", "MN", "55401", "612"), ("San Diego", "CA", "92101", "619"),
      ("Raleigh", "NC", "27601", "919"), ("Providence", "RI", "02903", "401"), ("Burlington", "VT", "05401", "802")]
UK = [("London", "", "EC1A 1BB"), ("Manchester", "", "M1 1AE"), ("Leeds", "", "LS1 4AP")]
CA = [("Toronto", "ON", "M5V 2T6", "416"), ("Vancouver", "BC", "V6B 1A1", "604")]


def pick_weighted(pairs):
    total = sum(w for _, w in pairs)
    x = R.uniform(0, total)
    for v, w in pairs:
        x -= w
        if x <= 0:
            return v
    return pairs[-1][0]


def messy_space(s, p=0.3):
    if not s or R.random() > p:
        return s
    k = R.randint(0, 3)
    if k == 0:
        return "  " + s
    if k == 1:
        return s + "   "
    if k == 2 and " " in s:
        return s.replace(" ", "  ", 1)
    return " " + s + " "


def messy_case(s):
    return pick_weighted([(s, 60), (s.upper(), 15), (s.lower(), 18), (s.swapcase(), 2), (s.capitalize(), 5)])


def fmt_date(d, t=None):
    serial = (dt.datetime.combine(d, dt.time()) - dt.datetime(1899, 12, 30)).days
    style = pick_weighted([("mdy", 30), ("iso", 20), ("iso_nopad", 8), ("long", 10), ("short", 7),
                           ("dmon", 5), ("serial", 8), ("isotime", 7), ("mdy2", 5)])
    if style == "mdy":
        return d.strftime("%m/%d/%Y")
    if style == "iso":
        return d.isoformat()
    if style == "iso_nopad":
        return f"{d.year}-{d.month}-{d.day}"
    if style == "long":
        return f"{d.strftime('%B')} {d.day} {d.year}"
    if style == "short":
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    if style == "dmon":
        return f"{d.day}-{d.strftime('%b')}-{d.strftime('%y')}"
    if style == "serial":
        return str(serial)
    if style == "isotime":
        return f"{d.isoformat()} {R.randint(7, 22):02d}:{R.randint(0, 59):02d}:{R.randint(0, 59):02d}"
    return f"{d.month}/{d.day}/{d.strftime('%y')}"


def fmt_money_us(v):
    return pick_weighted([(f"${v:,.2f}", 40), (f"{v:.2f}", 25), (f"USD {v:,.2f}", 10), (f"$ {v:.2f}".rstrip("0").rstrip("."), 10),
                          (f" {v:,.2f} ", 10), (f"{v:,.2f}", 5)])


# =================================================================== sample 1: customers
def phone_fmt(area, line, country):
    if country == "UK":
        n = f"07700 9{line:05d}"[:12]
        return pick_weighted([(n, 40), ("+44 " + n[1:], 30), ("+44 (0)" + n[1:], 10), (n.replace(" ", ""), 20)])
    num = f"{area}555{line:04d}"
    a, b, c = num[:3], num[3:6], num[6:]
    return pick_weighted([(f"({a}) {b}-{c}", 30), (f"{a}.{b}.{c}", 15), (f"{a}{b}{c}", 15), (f"+1 {a} {b} {c}", 12),
                          (f"1-{a}-{b}-{c}", 10), (f"{a}-{b}-{c}", 13), (f"{a}-{b}-{c} x{R.randint(10, 299)}", 5)])


def make_customers():
    used_lines = {}
    customers = []
    names_seen = set()
    for n in range(280):
        while True:
            fn, ln = R.choice(FIRST), R.choice(LAST)
            if (fn, ln) not in names_seen:
                names_seen.add((fn, ln))
                break
        country = pick_weighted([("US", 86), ("UK", 8), ("CA", 6)])
        if country == "US":
            city, state, zipc, area = R.choice(US)
        elif country == "UK":
            city, state, zipc = R.choice(UK)
            area = "07700"
        else:
            city, state, zipc, area = R.choice(CA)
        pool = used_lines.setdefault(area, list(range(100, 200)) if country != "UK" else list(range(900000, 900999)))
        line = pool.pop(R.randrange(len(pool)))
        if country == "UK":
            line = line - 900000
        domain = R.choice(["example.com", "example.net", "example.org"])
        style = R.randint(0, 3)
        base = ln.lower().replace("'", "").replace(" ", "")
        local = [f"{fn.lower()}.{base}", f"{fn.lower()}{base}{R.randint(1, 99)}", f"{fn[0].lower()}.{base}",
                 f"{fn.lower()}_{base}"][style]
        signup = dt.date(2023, 1, 1) + dt.timedelta(days=R.randint(0, 1338))
        orders = pick_weighted([(0, 8), (1, 25), (2, 20), (3, 15), (4, 10), (5, 8), (7, 6), (10, 5), (14, 3)])
        spent = Decimal(0) if orders == 0 else (Decimal(orders) * Decimal(str(R.uniform(18, 140)))).quantize(Decimal("0.01"))
        customers.append({"id": f"C-{10001 + n}", "first": fn, "last": ln, "email": f"{local}@{domain}",
                          "country": country, "city": city, "state": state, "zip": zipc, "area": area,
                          "line": line, "signup": signup, "orders": orders, "spent": spent,
                          "news": R.random() < 0.55})
    return customers


def render_customer(c, mess=True):
    country_txt = {"US": pick_weighted([("USA", 30), ("United States", 25), ("US", 20), ("U.S.", 10), ("usa", 10),
                                        ("United States of America", 5)]),
                   "UK": pick_weighted([("UK", 40), ("United Kingdom", 30), ("uk", 15), ("England", 15)]),
                   "CA": pick_weighted([("Canada", 60), ("canada", 25), ("CAN", 15)])}[c["country"]]
    email = c["email"]
    r = R.random()
    if r < 0.12:
        email = email.upper() if R.random() < 0.3 else email.split("@")[0].capitalize() + "@" + email.split("@")[1]
    elif r < 0.15:
        email = email.replace(".com", ".con").replace(".net", ".nte")
    elif r < 0.17:
        email = email.replace(".com", ",com").replace(".org", ",org")
    elif r < 0.19:
        email = "mailto:" + email
    elif r < 0.205:
        email = email.replace("@", "")         # invalid: must be flagged, not guessed
    phone = phone_fmt(c["area"], c["line"], c["country"])
    r = R.random()
    if r < 0.025:
        phone = f"555-01{R.randint(0, 99):02d}"   # 7 digits, no area code: flagged
    elif r < 0.045:
        phone = pick_weighted([("N/A", 1), ("", 1), ("-", 1)])
    orders_txt = str(c["orders"]) if R.random() > 0.05 else f" {c['orders']} "
    spent_txt = fmt_money_us(c["spent"]) if c["orders"] else pick_weighted([("0.00", 2), ("", 1), ("N/A", 1), ("$0.00", 2)])
    news = pick_weighted([("Yes", 30), ("yes", 15), ("Y", 15), ("TRUE", 10), ("y", 5)]) if c["news"] else \
        pick_weighted([("No", 30), ("no", 15), ("N", 15), ("FALSE", 10), ("n", 5)])
    state = c["state"]
    if state:
        state = pick_weighted([(state, 70), (state.lower(), 20), (state.capitalize(), 10)])
    row = [c["id"], messy_space(messy_case(c["first"])), messy_space(messy_case(c["last"])), messy_space(email, 0.15),
           messy_space(phone, 0.1), fmt_date(c["signup"]), messy_space(messy_case(c["city"]), 0.2), messy_space(state, 0.1),
           messy_space(country_txt, 0.15), c["zip"], orders_txt, spent_txt, news]
    return row


def write_customers():
    cust = make_customers()
    rows = [render_customer(c) for c in cust]
    # 14 exact duplicates: the same record exported twice (formatting may differ, values identical)
    for c in R.sample(cust[:260], 14):
        c2 = dict(c)
        rows.append(render_customer(c2))
    # 10 same-email duplicates: customer signed up twice (new ID, fewer details, later date)
    nxt = 10281
    for c in R.sample(cust[:260], 10):
        c2 = dict(c, id=f"C-{nxt}", signup=c["signup"] + dt.timedelta(days=R.randint(20, 200)), orders=0,
                  spent=Decimal(0))
        nxt += 1
        r = render_customer(c2)
        r[3] = "  " + c["email"].upper() + " "
        r[4] = ""
        r[12] = ""
        rows.append(r)
    # 5 near-duplicates: same person, name spelled differently + new email -> flag, never auto-remove
    variants = {"Olivia": "Olivea", "Sophia": "Sofia", "Isaac": "Issac", "Nathan": "Nathen", "Lily": "Lilly",
                "Hannah": "Hanna", "Amelia": "Amelie", "Grace": "Gracie", "Julian": "Julien", "Owen": "Owan",
                "Talia": "Thalia", "Clara": "Klara", "Felix": "Feliks", "Aria": "Arya", "Zoe": "Zoey"}
    cand = [c for c in cust[:260] if c["first"] in variants]
    for c in R.sample(cand, 5):
        c2 = dict(c, id=f"C-{nxt}", first=variants[c["first"]], email=f"{variants[c['first']].lower()}.{c['last'].lower().replace(' ', '').replace(chr(39), '')}@example.net")
        nxt += 1
        rows.append(render_customer(c2))
    R.shuffle(rows)
    rows.insert(R.randint(50, 120), [""] * 13)
    rows.insert(R.randint(180, 250), [""] * 13)
    header = ["Customer ID", " First Name", "last name", "E-mail", "Phone #", "Signup Date", "City", "State",
              "Country", "Zip", "Orders", "Total Spent", "Newsletter"]
    out = os.path.join(ROOT, "01-customer-list", "before_customers_messy.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Customer export - online store admin - 2026-09-01"])
        w.writerow([])
        w.writerow(header)
        w.writerows(rows)
    print(f"customers: {len(rows)} data rows (incl. 2 blank) -> {out}")


# =================================================================== sample 3: sales merge
PRODUCTS = [("Cold Brew Concentrate 1L", 18.00), ("Oat Milk Barista 6-pack", 21.50), ("Espresso Beans 1kg", 32.00),
            ("Decaf Beans 500g", 17.25), ("Ceramic Mug 12oz", 9.50), ("Paper Cups 12oz (50)", 11.75),
            ("Vanilla Syrup 750ml", 13.40), ("Caramel Syrup 750ml", 13.40), ("Pour-Over Kit", 44.00),
            ("Milk Frother", 58.00), ("Tea Sampler Box", 24.90), ("Gift Card $50", 50.00)]
REGIONS = ["Northeast", "South", "Midwest", "West"]
REGION_MESS = {"Northeast": ["Northeast", "northeast", "NE", "North East", "North-East", "NORTHEAST"],
               "South": ["South", "south", "SOUTH", "S", "Southern"],
               "Midwest": ["Midwest", "midwest", "Mid-West", "MW", "Mid West"],
               "West": ["West", "west", "WEST", "W", "West Coast"]}
CUSTOMERS = ["Maple Street Deli", "Harbor View Cafe", "Cedar & Stone Bakery", "Blue Door Coffee", "Northside Books & Brew",
             "Lantern Tea House", "Copper Kettle Diner", "Sunrise Bagel Co.", "Riverbend Market", "Oak Hollow Inn",
             "Parkside Juice Bar", "Twin Pines Grocery", "Driftwood Kitchen", "Morning Glory Cafe", "Juniper Hall Catering",
             "Brick Lane Roasters", "Summit Co-op", "Willow Creek Deli", "Hilltop Espresso", "Foxglove Patisserie"]


def q2(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def make_orders(prefix, start_no, n, qty_range):
    orders = []
    for k in range(n):
        d = dt.date(2026, 1, 1) + dt.timedelta(days=R.randint(0, 180))
        prod, price = R.choice(PRODUCTS)
        qty = R.randint(*qty_range)
        region = pick_weighted([("Northeast", 30), ("South", 25), ("Midwest", 20), ("West", 25)])
        net = q2(Decimal(str(price)) * qty)
        orders.append({"id": f"{prefix}-{start_no + k}", "date": d, "time": (R.randint(7, 21), R.randint(0, 59)),
                       "customer": R.choice(CUSTOMERS), "region": region, "product": prod, "qty": qty,
                       "price": q2(price), "net": net})
    orders.sort(key=lambda o: o["date"])
    return orders


def write_sales():
    import openpyxl
    web = make_orders("WS", 10001, 420, (1, 12))
    wh = make_orders("WH", 5001, 160, (10, 80))
    outdir = os.path.join(ROOT, "03-sales-merge")
    os.makedirs(outdir, exist_ok=True)
    # --- webstore CSV: US style
    path_csv = os.path.join(outdir, "before_webstore_orders.csv")
    with open(path_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Order ID", "Order Date", "Customer", "Region", "Product", "Qty", "Unit Price", "Net Total"])
        for o in web:
            d = o["date"]
            date_txt = pick_weighted([(f"{d:%m/%d/%Y} {o['time'][0]:02d}:{o['time'][1]:02d}", 50), (d.isoformat(), 30),
                                      (f"{d:%m/%d/%Y}", 20)])
            w.writerow([o["id"], date_txt, messy_space(o["customer"], 0.15), messy_space(R.choice(REGION_MESS[o["region"]]), 0.2),
                        o["product"], o["qty"], f"${o['price']:.2f}", fmt_money_us(o["net"])])
        # 6 exact re-exported rows (duplicated lines in the export)
        for o in R.sample(web, 6):
            d = o["date"]
            w.writerow([o["id"], d.isoformat(), o["customer"], o["region"], o["product"], o["qty"], f"${o['price']:.2f}",
                        f"${o['net']:,.2f}"])
    # --- wholesale XLSX: EU locale export (DD/MM/YYYY text, decimal comma), title rows, overlap
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales Export"
    ws.append(["Wholesale sales export"])
    ws.append(["Period: 01/01/2026 - 30/06/2026"])
    ws.append([])
    ws.append(["Order Ref", "Date", "Sales Region", "Client", "Item", "Units", "Unit Price", "Total"])

    def eu(v):
        s = f"{v:,.2f}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    rows = []
    for o in wh:
        d = o["date"]
        date_val = pick_weighted([(d.strftime("%d/%m/%Y"), 70), (dt.datetime.combine(d, dt.time()), 20), (d.strftime("%d.%m.%Y"), 10)])
        rows.append([o["id"], date_val, R.choice(REGION_MESS[o["region"]]), o["customer"].upper() if R.random() < 0.3 else o["customer"],
                     o["product"], o["qty"], eu(o["price"]), eu(o["net"]) + pick_weighted([("", 3), (" €", 0), (" USD", 1)])])
    # 28 webstore B2B orders that the wholesale team also logged (same order, different formatting)
    overlap = R.sample([o for o in web if o["qty"] >= 3], 28)
    for o in overlap:
        d = o["date"]
        rows.append([pick_weighted([(o["id"].lower(), 1), (o["id"] + " ", 1), (o["id"].replace("-", ""), 1)]), d.strftime("%d/%m/%Y"),
                     R.choice(REGION_MESS[o["region"]]), o["customer"], o["product"], o["qty"], eu(o["price"]), eu(o["net"])])
    R.shuffle(rows)
    for r in rows:
        ws.append(r)
    for col, width in zip("ABCDEFGH", (12, 12, 14, 26, 26, 8, 11, 12)):
        ws.column_dimensions[col].width = width
    path_x = os.path.join(outdir, "before_wholesale_sales.xlsx")
    wb.save(path_x)
    # ground truth for the tests / QA: unique orders and their total
    truth = {o["id"]: o for o in web + wh}
    total = sum((o["net"] for o in truth.values()), Decimal(0))
    with open(os.path.join(HERE, "sales_truth.txt"), "w") as f:
        f.write(f"unique_orders={len(truth)}\ngrand_total={total}\n")
    print(f"sales: webstore {len(web) + 6} rows, wholesale {len(rows)} rows, unique orders {len(truth)}, total {total}")


if __name__ == "__main__":
    write_customers()
    write_sales()
