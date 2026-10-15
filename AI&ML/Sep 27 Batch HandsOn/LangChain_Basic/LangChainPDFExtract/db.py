import os
from pathlib import Path

import pymssql
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

SERVER = os.getenv("MSSQL_SERVER", "KEKEKE395B.local")
PORT = int(os.getenv("MSSQL_PORT", "1433"))
DATABASE = os.getenv("MSSQL_DATABASE", "ClassSchedules")
USER = os.getenv("MSSQL_USER")
PASSWORD = os.getenv("MSSQL_PASSWORD")


def get_connection(database=DATABASE, autocommit=False):
    if not USER or not PASSWORD:
        raise RuntimeError("Set MSSQL_USER and MSSQL_PASSWORD in course/ollama/.env")
    return pymssql.connect(
        server=SERVER,
        port=PORT,
        user=USER,
        password=PASSWORD,
        database=database,
        autocommit=autocommit,
        as_dict=True,
        login_timeout=10,
    )


def init_db():
    conn = get_connection("master", autocommit=True)
    try:
        conn.cursor().execute(f"IF DB_ID(N'{DATABASE}') IS NULL CREATE DATABASE [{DATABASE}]")
    finally:
        conn.close()

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            IF OBJECT_ID(N'dbo.PdfFiles', N'U') IS NULL
            CREATE TABLE dbo.PdfFiles (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                FileName NVARCHAR(260) NOT NULL UNIQUE,
                ProcessedAt DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
            )
        """)
        cur.execute("IF OBJECT_ID(N'dbo.Classes', N'U') IS NOT NULL DROP TABLE dbo.Classes")
        cur.execute("""
            IF OBJECT_ID(N'dbo.ScheduleItems', N'U') IS NULL
            CREATE TABLE dbo.ScheduleItems (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                PdfId INT NOT NULL REFERENCES dbo.PdfFiles(Id) ON DELETE CASCADE,
                Title NVARCHAR(300) NOT NULL,
                Category NVARCHAR(100) NULL,
                EventDate DATE NULL,
                DayOfWeek NVARCHAR(10) NULL,
                StartTime TIME(0) NULL,
                EndTime TIME(0) NULL,
                Location NVARCHAR(200) NULL
            )
        """)
        cur.execute("""
            CREATE OR ALTER VIEW dbo.vBusyness AS
            SELECT COALESCE(DayOfWeek, DATENAME(WEEKDAY, EventDate)) AS DayName,
                   COUNT(*) AS Items,
                   CAST(SUM(CASE WHEN StartTime IS NOT NULL AND EndTime > StartTime
                                 THEN DATEDIFF(MINUTE, StartTime, EndTime) ELSE 0 END) / 60.0
                        AS DECIMAL(9,2)) AS TotalHours
            FROM dbo.ScheduleItems
            WHERE COALESCE(DayOfWeek, DATENAME(WEEKDAY, EventDate)) IS NOT NULL
            GROUP BY COALESCE(DayOfWeek, DATENAME(WEEKDAY, EventDate))
        """)
        conn.commit()


def is_processed(file_name):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 AS found FROM dbo.PdfFiles WHERE FileName = %s", (file_name,))
        return cur.fetchone() is not None


def save_items(file_name, items):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.PdfFiles WHERE FileName = %s", (file_name,))
        cur.execute(
            "INSERT INTO dbo.PdfFiles (FileName) OUTPUT INSERTED.Id AS Id VALUES (%s)", (file_name,)
        )
        pdf_id = cur.fetchone()["Id"]
        if items:
            cur.executemany(
                "INSERT INTO dbo.ScheduleItems (PdfId, Title, Category, EventDate, DayOfWeek, StartTime, EndTime, Location)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (pdf_id, i["title"], i["category"], i["event_date"], i["day_of_week"],
                     i["start_time"], i["end_time"], i["location"])
                    for i in items
                ],
            )
        conn.commit()
    return len(items)


def get_items(file_name=None):
    query = """
        SELECT p.FileName AS file_name, s.Title AS title, s.Category AS category,
               s.EventDate AS event_date, s.DayOfWeek AS day_of_week,
               s.StartTime AS start_time, s.EndTime AS end_time, s.Location AS location
        FROM dbo.ScheduleItems s JOIN dbo.PdfFiles p ON p.Id = s.PdfId
    """
    params = ()
    if file_name:
        query += " WHERE p.FileName = %s"
        params = (file_name,)
    query += " ORDER BY p.FileName, s.EventDate, s.DayOfWeek, s.StartTime, s.Title"
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()


def get_busyness():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DayName, Items, TotalHours FROM dbo.vBusyness")
        return cur.fetchall()


def get_files():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.FileName AS file_name, p.ProcessedAt AS processed_at, COUNT(c.Id) AS item_count
            FROM dbo.PdfFiles p LEFT JOIN dbo.ScheduleItems c ON c.PdfId = p.Id
            GROUP BY p.Id, p.FileName, p.ProcessedAt ORDER BY p.ProcessedAt DESC
        """)
        return cur.fetchall()


def init_public_schedule():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            IF OBJECT_ID(N'dbo.PublicSchedule', N'U') IS NULL
            CREATE TABLE dbo.PublicSchedule (
                Id INT IDENTITY(1,1) PRIMARY KEY,
                Agency NVARCHAR(50) NOT NULL,
                RouteLine NVARCHAR(100) NOT NULL,
                DayType NVARCHAR(20) NULL,
                TrainNumber NVARCHAR(20) NULL,
                DepartTime TIME(0) NULL,
                ArriveTime TIME(0) NULL,
                RouteDesc NVARCHAR(200) NULL,
                EffectiveDate DATE NULL,
                SourceFile NVARCHAR(260) NOT NULL,
                ProcessedAt DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
            )
        """)
        conn.commit()


def clear_public_schedule(source_file):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.PublicSchedule WHERE SourceFile = %s", (source_file,))
        conn.commit()


def save_public_schedule(agency, route_line, day_type, effective_date, source_file, items):
    clear_public_schedule(source_file)
    with get_connection() as conn:
        cur = conn.cursor()
        if items:
            cur.executemany(
                "INSERT INTO dbo.PublicSchedule"
                " (Agency, RouteLine, DayType, TrainNumber, DepartTime, ArriveTime, RouteDesc, EffectiveDate, SourceFile)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (agency, route_line, day_type, i["train_number"], i["depart_time"],
                     i["arrive_time"], i["route_desc"], effective_date, source_file)
                    for i in items
                ],
            )
        conn.commit()
    return len(items)


def get_public_schedule():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT Agency, RouteLine, DayType, TrainNumber, DepartTime, ArriveTime,
                   RouteDesc, EffectiveDate, SourceFile
            FROM dbo.PublicSchedule
            ORDER BY RouteLine, DayType, DepartTime
        """)
        return cur.fetchall()


if __name__ == "__main__":
    init_db()
    init_public_schedule()
    print(f"Connected to {SERVER}:{PORT}, database [{DATABASE}].")
    print("Tables ready: dbo.PdfFiles, dbo.ScheduleItems, dbo.PublicSchedule, view dbo.vBusyness.")
