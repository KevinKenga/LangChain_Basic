Understanding of Files
requirement.txt: list of libraries, that I need for this pipeline
then run: source venv/bin/activate
pip install -r requirements.txt
go to .env file:
    OPENAI_API_KEY=xxxxxxx
    GITHUB_TOKEN=xxxx
    MSSQL_SERVER=xxxxxxx
    MSSQL_PORT=xxxxxx
    MSSQL_DATABASE=xxxxxxx
    MSSQL_USER=xxxxxxxx
    MSSQL_PASSWORD=xxxxxxxx

## What this pipeline does

Downloads real 2026 PDF train timetables from NJ TRANSIT's public site,
extracts the schedule rows (train number, depart/arrive time, route) using
OpenAI, and saves them into a SQL Server table called `dbo.PublicSchedule`.

Files:
- `main.py` — the pipeline: download PDFs -> extract text -> ask OpenAI to
  structure it -> save to SQL Server. Run this one.
- `db.py` — all SQL Server code (connection, create tables, insert, read).
  Imported by `main.py`, not run directly (except for `python db.py`
  which just (re)creates the tables).
- `pdfs/` — downloaded PDF files land here (ignored by git).
- `requirements.txt` — third-party packages to install (standard-library
  imports like `datetime` and `pathlib` don't need to be listed, Python
  already includes them).

## 1. Create and activate a virtual environment

```bash
cd course/LangChainPDFExtract
python3 -m venv venv
source venv/bin/activate
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Fill in the .env file

Create/edit `.env` in this folder with your real values:

```
OPENAI_API_KEY=xxxxxxx
MSSQL_SERVER=xxxxxxx
MSSQL_PORT=1433
MSSQL_DATABASE=Schedules
MSSQL_USER=xxxxxxxx
MSSQL_PASSWORD=xxxxxxxx
```

`OPENAI_API_KEY` is used to call the OpenAI model (`gpt-4o-mini`) that turns
the raw PDF text into structured rows. The `MSSQL_*` values point to the SQL
Server database/table where results are saved.

## 4. Create the database table

The first time, create the `dbo.PublicSchedule` table (and the other
tables used in this course) by running:

```bash
python db.py
```

Expected output:
```
Connected to <server>:1433, database [Schedules].
Tables ready: dbo.PdfFiles, dbo.ScheduleItems, dbo.PublicSchedule, view dbo.vBusyness.
```

## 5. Run the pipeline

```bash
python main.py
```

This will, in order:
1. Download 3 real NJ TRANSIT 2026 weekday PDF timetables into `pdfs/`
   (Northeast Corridor, Raritan Valley, Pascack Valley) — skipped if already
   downloaded.
2. Extract the text of each PDF with `pypdf`.
3. Send that text to OpenAI (`gpt-4o-mini`) with a prompt asking for a
   Markdown table of Train / Depart / Arrive / Description.
4. Parse that table and save the rows into `dbo.PublicSchedule`
   (replacing any existing rows for that same PDF file).
5. Print a summary table of everything currently stored.

## 6. Verify the data in SQL Server

```sql
SELECT COUNT(*) FROM dbo.PublicSchedule;
SELECT TOP 20 * FROM dbo.PublicSchedule ORDER BY RouteLine, DepartTime;
```

## Adding more timetables

To pull additional lines, add entries to the `SOURCES` list in `main.py`
with the agency name, line name, day type, effective date, and the direct
PDF URL (found on https://www.njtransit.com/schedules/printable). Delete the
corresponding file in `pdfs/` if you want to force a re-download.

## Notes / gotchas

- `.env` is git-ignored on purpose — never commit real secrets.
- `dbo.PublicSchedule` is separate from `dbo.ScheduleItems` (an older,
  unrelated class-schedule exercise from this course).
- This pipeline no longer uses Ollama/local models — all extraction goes
  through the OpenAI API, so `OPENAI_API_KEY` must be valid and have quota.