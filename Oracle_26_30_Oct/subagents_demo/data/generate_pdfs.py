"""
=====================================================================
FILE: data/generate_pdfs.py
=====================================================================
PURPOSE
    Creates the 2 input PDFs for the subagents demo:
        1. job_description.pdf   - what the company wants
        2. candidate_resume.pdf  - what the candidate has

WHAT PROBLEM IT SOLVES
    Gives the subagents realistic (fake) documents to work on, without
    using any real person's data.

HOW TO RUN
    From the project root:
        python data/generate_pdfs.py

EXPECTED OUTPUT
    Created data/pdfs/job_description.pdf
    Created data/pdfs/candidate_resume.pdf
=====================================================================
"""

# Path gives OS-independent file paths.
from pathlib import Path

# A4 page size.
from reportlab.lib.pagesizes import A4

# Ready-made text styles (Title, Heading2, BodyText).
from reportlab.lib.styles import getSampleStyleSheet

# SimpleDocTemplate builds the PDF; Paragraph = text block; Spacer = gap.
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


# Output folder: data/pdfs next to this script.
PDF_DIR = Path(__file__).resolve().parent / "pdfs"

# Job description content as (style, text) pairs.
JOB_DESCRIPTION = [
    ("title", "Job Description - Data Engineer (Mid-level)"),
    ("p", "Company: Kestrel Logistics, Pune. Team: Data Platform. Mode: Hybrid, 3 days in office."),
    ("h", "Must-have skills"),
    ("p", "3 or more years of experience as a data engineer. Strong Python and SQL. "
          "Hands-on experience with Apache Spark. Experience building pipelines on AWS (S3, Glue, Redshift). "
          "Experience with Airflow for scheduling pipelines."),
    ("h", "Good-to-have skills"),
    ("p", "Kafka for streaming data. dbt for data transformations. Docker. "
          "Any exposure to logistics or supply chain data."),
    ("h", "Responsibilities"),
    ("p", "Build and maintain daily pipelines that move shipment data from operational databases into Redshift. "
          "Improve pipeline reliability and reduce failed runs. Work with analysts to model data for dashboards."),
    ("h", "Compensation and notice"),
    ("p", "Budget is 18 to 24 lakh per year. Preferred notice period is 30 days or less."),
]

# Resume content as (style, text) pairs.
CANDIDATE_RESUME = [
    ("title", "Resume - Ananya Rao"),
    ("p", "Location: Pune. Current role: Data Engineer at Brightcart (e-commerce). Notice period: 60 days."),
    ("h", "Experience"),
    ("p", "Brightcart, Data Engineer, 2022 to present (3.5 years): built Spark jobs on AWS EMR that process "
          "12 million orders a day. Moved 40 pipelines from cron scripts to Airflow, cutting failed runs by 60 percent. "
          "Loaded curated data into Redshift for the finance and supply teams."),
    ("p", "Brightcart, Data Analyst, 2021 to 2022 (1 year): wrote SQL reports and Tableau dashboards "
          "for warehouse and delivery performance."),
    ("h", "Skills"),
    ("p", "Python, SQL, PySpark, AWS (S3, EMR, Redshift, Lambda), Airflow, Docker, Git, Tableau. "
          "Basic Kafka from a personal project. No dbt experience."),
    ("h", "Education"),
    ("p", "B.E. Computer Engineering, Savitribai Phule Pune University, 2021."),
]


def build_pdf(filename: str, blocks: list) -> None:
    """Write one PDF from a list of (style, text) pairs."""
    # Full path of the output file.
    out_path = PDF_DIR / filename
    # Create the PDF document object.
    doc = SimpleDocTemplate(str(out_path), pagesize=A4)
    # Load default styles.
    styles = getSampleStyleSheet()
    # Map our short names to ReportLab styles.
    style_map = {"title": styles["Title"], "h": styles["Heading2"], "p": styles["BodyText"]}
    # Build the list of things to draw: each text block followed by a small gap.
    story = []
    # Go through each block.
    for style_name, text in blocks:
        # Add the paragraph.
        story.append(Paragraph(text, style_map[style_name]))
        # Add a 6-point gap after it.
        story.append(Spacer(1, 6))
    # Write the PDF to disk.
    doc.build(story)
    # Confirm what was created.
    print(f"Created data/pdfs/{filename}")


# Run only when executed directly.
if __name__ == "__main__":
    # Create the output folder if needed.
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    # Build PDF 1.
    build_pdf("job_description.pdf", JOB_DESCRIPTION)
    # Build PDF 2.
    build_pdf("candidate_resume.pdf", CANDIDATE_RESUME)
