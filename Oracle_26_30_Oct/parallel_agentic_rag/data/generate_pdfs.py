"""
=====================================================================
FILE: data/generate_pdfs.py
=====================================================================
PURPOSE
    Creates the 3 synthetic product-management PDFs that our RAG
    system will search:
        1. customer_feedback_report.pdf   (Customer Success team)
        2. product_usage_analytics.pdf    (Data / Analytics team)
        3. competitor_analysis.pdf        (Product Marketing team)

WHAT PROBLEM IT SOLVES
    We need realistic company documents for a demo, but real product
    reports are confidential. This script writes fake (but consistent)
    numbers about the fictional company "NimbusDesk".
    It also plants "keyword trap" paragraphs: paragraphs that contain
    words like "WhatsApp" or "AI" but are NOT about the product.
    These traps let students see re-ranking fix bad vector-search hits.

HOW TO RUN
    From the project root (the folder that contains README.md):
        python data/generate_pdfs.py

EXPECTED OUTPUT
    Three PDF files inside data/pdfs/ and this printed line per file:
        Created data/pdfs/customer_feedback_report.pdf (3 pages)
=====================================================================
"""

# Path gives us OS-independent file paths (works on Windows, Mac, Linux).
from pathlib import Path

# A4 is the standard Indian/European page size (210 x 297 mm).
from reportlab.lib.pagesizes import A4

# getSampleStyleSheet gives ready-made text styles (Title, Heading, Body).
from reportlab.lib.styles import getSampleStyleSheet

# SimpleDocTemplate builds the PDF; Paragraph is a block of text;
# Spacer adds vertical gap; PageBreak forces a new page.
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak


# Folder where this script lives (…/data).
DATA_DIR = Path(__file__).resolve().parent
# Output folder for the PDFs (…/data/pdfs).
PDF_DIR = DATA_DIR / "pdfs"


# ---------------------------------------------------------------------
# CONTENT
# Each document is a list of pages. Each page is a list of
# (style_name, text) pairs. "h" = heading, "p" = normal paragraph.
# Paragraphs marked "TRAP" in comments are keyword traps for re-ranking.
# ---------------------------------------------------------------------

# Content for PDF 1: what customers say.
CUSTOMER_FEEDBACK = [
    # ---------------- Page 1 ----------------
    [
        ("title", "NimbusDesk Customer Feedback Report - Q3 2026"),
        ("p", "Prepared by the Customer Success team. This report summarises the Q3 2026 customer survey, "
              "support ticket themes and churn interviews. The survey received 412 responses from admins "
              "and agents across 1,200 paying accounts."),
        ("h", "1. Net Promoter Score"),
        ("p", "Net Promoter Score (NPS) fell from 38 in Q2 2026 to 31 in Q3 2026. The drop is concentrated in "
              "accounts with 11 to 50 seats, where NPS fell from 35 to 22. Accounts with 1 to 10 seats and "
              "accounts with more than 50 seats were broadly stable."),
        ("h", "2. Top feature requests"),
        ("p", "The most requested feature is AI-suggested ticket replies, requested by 187 respondents. "
              "Second is a WhatsApp integration, requested by 164 respondents. Third is SLA breach alerts, "
              "requested by 121 respondents. Dark mode was requested by 44 respondents."),
        ("p", "Agents who asked for AI-suggested replies said they spend roughly 40 percent of their working "
              "day typing answers to repeated questions such as password resets, refund status and delivery "
              "delays. Several admins said faster first replies are the main thing their own customers judge them on."),
        ("p", "Of the 164 WhatsApp integration requests, 61 percent came from accounts with 11 to 50 seats, "
              "mostly retail and D2C brands in India and Brazil. These customers say their own buyers already "
              "message them on WhatsApp and the conversations stay outside NimbusDesk, so nothing is tracked."),
    ],
    # ---------------- Page 2 ----------------
    [
        ("h", "3. Support ticket themes"),
        ("p", "Across 6,300 support tickets raised by our customers to NimbusDesk support in Q3, the top themes were: "
              "slow search inside large ticket histories (22 percent), confusion about SLA settings (17 percent), "
              "reporting and export limits (14 percent) and billing questions (11 percent)."),
        ("h", "4. Churn interviews"),
        ("p", "We interviewed 23 accounts that cancelled in Q3. Nine said the lack of a WhatsApp channel was the main "
              "reason they left. Six said their agents were too slow and a competitor helped them reply faster. "
              "Four cited price. Four cited other reasons such as company closure."),
        # TRAP: mentions WhatsApp, but is about our internal team, not the product.
        ("h", "5. Customer Success team operations"),
        ("p", "Internal note: the Customer Success team currently coordinates weekend shift swaps and on-call cover "
              "through a WhatsApp group. Because messages get lost, the team plans to move shift coordination to a "
              "dedicated Slack channel in November. This note concerns internal staffing only."),
        # TRAP: mentions AI and replies, but is about a conference.
        ("p", "Two Customer Success managers attended an AI customer experience conference in Singapore in September. "
              "Talks covered AI chatbots, AI reply tone and AI in call centres. Travel costs were within budget and "
              "the team shared slides internally."),
    ],
    # ---------------- Page 3 ----------------
    [
        ("h", "6. Customer concerns and risks"),
        ("p", "Not every customer wants automation. 38 percent of respondents from accounts with more than 50 seats "
              "said they would only use AI-suggested replies if a human must approve each reply before it is sent. "
              "Several worried about wrong answers going to their customers and damaging trust."),
        ("p", "On WhatsApp, 27 percent of interested respondents asked who pays the WhatsApp Business API "
              "per-conversation fees. Many said they would not pay more than 10 percent extra per agent for it. "
              "A few raised data privacy questions about storing WhatsApp chats in NimbusDesk."),
        ("h", "7. Summary from Customer Success"),
        ("p", "Customer Success recommends treating faster replies and a WhatsApp channel as the two biggest drivers "
              "of satisfaction for the 11 to 50 seat segment, while keeping human approval as an option for larger accounts."),
    ],
]

# Content for PDF 2: what the numbers say.
USAGE_ANALYTICS = [
    # ---------------- Page 1 ----------------
    [
        ("title", "NimbusDesk Product Usage Analytics - Q3 2026"),
        ("p", "Prepared by the Data and Analytics team. All numbers are for July to September 2026 unless stated."),
        ("h", "1. Accounts and churn by segment"),
        ("p", "NimbusDesk has 1,200 paying accounts and 9,800 monthly active agents. Segment 1 to 10 seats has "
              "520 accounts with monthly churn of 2.1 percent. Segment 11 to 50 seats has 480 accounts and its "
              "monthly churn rose from 1.4 percent in June to 2.9 percent in September. Segment 51 plus seats has "
              "200 accounts with monthly churn of 0.8 percent."),
        ("h", "2. Response times"),
        ("p", "Median first response time across all accounts is 4 hours 12 minutes. In the 11 to 50 seat segment "
              "it is 5 hours 40 minutes, the slowest of any segment. Canned responses are used by 72 percent of "
              "agents, but advanced macros by only 18 percent, which suggests agents still type most replies by hand."),
    ],
    # ---------------- Page 2 ----------------
    [
        ("h", "3. Channels and retention"),
        ("p", "Ticket volume by channel is email 64 percent, web form 22 percent and live chat 14 percent. "
              "Accounts that connect at least one messaging channel in their first 30 days keep 91 percent of "
              "their seats after six months, compared with 74 percent for email-only accounts."),
        ("p", "In accounts that requested WhatsApp, admins estimate that 35 percent of their end customers already "
              "contact them through WhatsApp outside NimbusDesk. These conversations are invisible in our reports."),
        # TRAP: says "replies" and "open rates" but is about email tracking analytics.
        ("h", "4. Email engagement tracking"),
        ("p", "Our outbound product newsletter reached 8,200 admins. Email replies to the newsletter were tracked "
              "with a reply-tracking tag, and the open rate was 47 percent. Reply volume to marketing emails rose "
              "after we changed the subject lines in August."),
        # TRAP: performance number unrelated to features.
        ("p", "After the database migration in August, the agent dashboard page load time improved from 3.1 seconds "
              "to 1.4 seconds. No customer-facing downtime was recorded during the migration."),
    ],
    # ---------------- Page 3 ----------------
    [
        ("h", "5. SLA breaches"),
        ("p", "18 percent of tickets in the 11 to 50 seat segment breached their SLA in Q3, compared with 7 percent "
              "in other segments. Accounts with more than 20 percent SLA breaches were three times more likely to churn."),
        ("h", "6. AI draft replies pilot"),
        ("p", "In August we piloted AI draft replies with 30 accounts. Median first response time fell by 34 percent. "
              "Agents accepted 58 percent of AI drafts as written and edited the other 42 percent before sending. "
              "No pilot account reported a wrong reply reaching a customer, because every draft needed a click to send."),
        ("p", "The estimated model cost for AI draft replies is about 0.6 US dollars per agent per month at current "
              "ticket volumes, which is small compared with the per-agent price."),
    ],
]

# Content for PDF 3: what competitors do.
COMPETITOR_ANALYSIS = [
    # ---------------- Page 1 ----------------
    [
        ("title", "NimbusDesk Competitor Analysis - Q3 2026"),
        ("p", "Prepared by Product Marketing. We track three competitors: HelixDesk (large enterprise suite), "
              "Freshline (mid-market helpdesk) and ReplyPilot (new AI-first startup)."),
        ("h", "1. Pricing per agent per month"),
        ("p", "NimbusDesk costs 19 US dollars per agent per month. Freshline costs 29 dollars, ReplyPilot 25 dollars "
              "and HelixDesk 55 dollars. NimbusDesk remains the cheapest full helpdesk in the market."),
        ("h", "2. Feature comparison"),
        ("p", "WhatsApp channel: HelixDesk and Freshline both offer WhatsApp, but only on their higher pricing tiers. "
              "ReplyPilot does not offer WhatsApp yet. NimbusDesk does not offer WhatsApp."),
        ("p", "AI-suggested replies: all three competitors offer them. ReplyPilot makes AI replies its core feature "
              "and can auto-send replies without a human. HelixDesk sells AI replies as a 50 dollar per agent add-on. "
              "Freshline includes basic AI drafts in its middle tier. NimbusDesk does not offer AI replies."),
    ],
    # ---------------- Page 2 ----------------
    [
        ("h", "3. Win / loss analysis"),
        ("p", "In Q3 NimbusDesk lost 41 deals that reached the final stage. 17 were lost to Freshline, and the main "
              "reason given was the WhatsApp channel. 12 were lost to ReplyPilot, and the main reason given was AI "
              "replies. 8 were lost to HelixDesk, mostly large companies needing enterprise compliance features."),
        # TRAP: WhatsApp mentioned but about a marketing campaign, not product capability.
        ("h", "4. Competitor marketing activity"),
        ("p", "Freshline ran a WhatsApp sticker campaign during Diwali and sponsored two SaaS meetups in Bengaluru. "
              "Their social media following grew by about 12 percent. This was a brand campaign and did not "
              "announce any new product capability."),
    ],
    # ---------------- Page 3 ----------------
    [
        ("h", "5. Market threats"),
        ("p", "ReplyPilot raised a Series A round in September and has said it will target 11 to 50 seat businesses "
              "in India in 2027. If it adds WhatsApp, it would match both of our top missing features at a similar price."),
        ("p", "WhatsApp Business API per-conversation fees in India range from roughly 0.35 to 0.80 rupees and have "
              "risen twice in the past year. Any WhatsApp feature must decide whether these fees are passed to customers."),
        ("h", "6. Positioning recommendation"),
        ("p", "Product Marketing believes NimbusDesk can keep its price advantage if it adds AI-suggested replies "
              "with human approval, which ReplyPilot does not emphasise and which larger customers ask for."),
    ],
]


def build_pdf(filename: str, pages: list) -> None:
    """Write one PDF from a list of pages."""
    # Full output path, e.g. data/pdfs/customer_feedback_report.pdf.
    out_path = PDF_DIR / filename
    # Create the document object with A4 pages.
    doc = SimpleDocTemplate(str(out_path), pagesize=A4)
    # Load the default text styles.
    styles = getSampleStyleSheet()
    # Map our short style names to ReportLab styles.
    style_map = {"title": styles["Title"], "h": styles["Heading2"], "p": styles["BodyText"]}
    # "story" is ReportLab's word for the ordered list of things to draw.
    story = []
    # Go through pages one at a time; enumerate gives us the page index too.
    for page_index, page in enumerate(pages):
        # Go through every (style, text) pair on this page.
        for style_name, text in page:
            # Add the text as a paragraph with the chosen style.
            story.append(Paragraph(text, style_map[style_name]))
            # Small gap after each block so text is readable.
            story.append(Spacer(1, 6))
        # Add a page break after every page except the last one.
        if page_index < len(pages) - 1:
            story.append(PageBreak())
    # Render the story into the PDF file on disk.
    doc.build(story)
    # Tell the user what was created.
    print(f"Created {out_path.relative_to(DATA_DIR.parent)} ({len(pages)} pages)")


def main() -> None:
    """Create the output folder and all three PDFs."""
    # Make data/pdfs if it doesn't exist; no error if it already does.
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    # Build PDF 1.
    build_pdf("customer_feedback_report.pdf", CUSTOMER_FEEDBACK)
    # Build PDF 2.
    build_pdf("product_usage_analytics.pdf", USAGE_ANALYTICS)
    # Build PDF 3.
    build_pdf("competitor_analysis.pdf", COMPETITOR_ANALYSIS)


# Run main() only when this file is executed directly, not when imported.
if __name__ == "__main__":
    main()
