"""
Pipeline: download real public transit PDF timetables, extract the schedule
rows with an OpenAI model, and save them into SQL Server (dbo.PublicSchedule).

Data source: NJ TRANSIT's public "Printer-Friendly Timetables" page
https://www.njtransit.com/schedules/printable (2026 weekday timetables).
"""
from datetime import datetime
from pathlib import Path

import requests
from openai import OpenAI
from pypdf import PdfReader

import db

MODEL = "gpt-4o-mini"
PDF_FOLDER = Path(__file__).resolve().parent / "pdfs"
client = OpenAI()  # reads OPENAI_API_KEY, set by db.py's load_dotenv() above

# agency, route line name, day type, direct PDF URL, effective date
SOURCES = [
    ("NJ TRANSIT", "Northeast Corridor", "Weekday", "2026-08-30",
     "https://content.njtransit.com/sites/default/files/NEC-WKDY-083026.pdf"),
    ("NJ TRANSIT", "Raritan Valley", "Weekday", "2026-08-30",
     "https://content.njtransit.com/sites/default/files/RVL-WKDY-083026.pdf"),
    ("NJ TRANSIT", "Pascack Valley", "Weekday", "2026-08-30",
     "https://content.njtransit.com/sites/default/files/PV-WKDY-083026.pdf"),
]


def download_pdfs():
    PDF_FOLDER.mkdir(exist_ok=True)
    paths = []
    for agency, route, day_type, eff_date, url in SOURCES:
        file_name = url.rsplit("/", 1)[-1]
        path = PDF_FOLDER / file_name
        if not path.exists():
            print(f"Downloading {file_name} ...")
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
            resp.raise_for_status()
            path.write_bytes(resp.content)
        else:
            print(f"Already downloaded: {file_name}")
        paths.append((agency, route, day_type, eff_date, path))
    return paths


def read_pdf_text(path):
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


TIME_FORMATS = ("%H:%M", "%I:%M %p", "%I:%M%p")


def parse_time(value):
    value = value.strip().upper().replace(".", "")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            pass
    return None


def clean(value, limit):
    value = " ".join(value.split())
    return value[:limit] if value and value not in ("-", "N/A", "n/a", "None") else None


def extract_items(text, route_name):
    prompt = f"""Below is the text of a real NJ TRANSIT PDF train timetable for the
"{route_name}" line. List every train run you can find as a Markdown table with
these 4 columns:
Train | Depart | Arrive | Description
- Train: the train number (if shown), otherwise empty.
- Depart: departure time in 24-hour HH:MM format.
- Arrive: arrival time in 24-hour HH:MM format, empty if unknown.
- Description: the origin/destination station names for that run.
Only include rows that represent an actual scheduled train run with a time.
Never invent data. Output only the table, nothing else.

PDF TEXT:
{text[:12000]}
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You extract data from documents accurately and never invent data."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    items = []
    seen = set()
    for line in response.choices[0].message.content.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0] + cells[1]) <= set("-: ") or cells[0].lower() == "train":
            continue
        depart = parse_time(cells[1])
        if not depart:
            continue
        item = {
            "train_number": clean(cells[0], 20),
            "depart_time": depart,
            "arrive_time": parse_time(cells[2]) if cells[2] else None,
            "route_desc": clean(cells[3], 200),
        }
        key = (item["train_number"], item["depart_time"])
        if key not in seen:
            seen.add(key)
            items.append(item)
    return items


def process(agency, route, day_type, eff_date, path):
    print(f"Extracting: {path.name} ({route})")
    text = read_pdf_text(path)
    items = extract_items(text, route)
    db.save_public_schedule(agency, route, day_type, eff_date, path.name, items)
    print(f"Saved {len(items)} rows from {path.name}")
    return items


if __name__ == "__main__":
    db.init_db()
    db.init_public_schedule()

    sources = download_pdfs()
    for agency, route, day_type, eff_date, path in sources:
        process(agency, route, day_type, eff_date, path)

    print()
    print(f"{'Agency':<12} | {'Line':<20} | {'DayType':<8} | {'Train':<8} | {'Depart':<6} | {'Arrive':<6} | Description")
    print("-" * 110)
    for r in db.get_public_schedule():
        print(f"{r['Agency']:<12} | {r['RouteLine'][:20]:<20} | {r['DayType'] or '':<8} | "
              f"{r['TrainNumber'] or '':<8} | {str(r['DepartTime'] or '')[:5]:<6} | "
              f"{str(r['ArriveTime'] or '')[:5]:<6} | {r['RouteDesc'] or ''}")
