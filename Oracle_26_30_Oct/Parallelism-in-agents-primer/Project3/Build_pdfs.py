"""One-off script that generates the two product-management PDFs the RAG reads.
Run once:  python3 build_pdfs.py
It writes docs/product_discovery.pdf and docs/product_metrics_launch.pdf.
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], fontSize=20, spaceAfter=14)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=12, spaceAfter=6)
BODY = ParagraphStyle("BODY", parent=styles["Normal"], fontSize=10.5, leading=15, spaceAfter=8)


def build(path, title, sections):
    doc = SimpleDocTemplate(path, pagesize=A4,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    story = [Paragraph(title, H1), Spacer(1, 6)]
    for heading, body in sections:
        story.append(Paragraph(heading, H2))
        story.append(Paragraph(body, BODY))
    doc.build(story)
    print("wrote", path)


discovery = [
    ("What product discovery is",
     "Product discovery is the work of deciding what to build before you build it. Its goal is to reduce the risk of "
     "shipping something nobody wants. A good discovery process answers four questions: is the problem real, is it "
     "valuable to solve, can we build the solution, and will it work for the business. Teams that skip discovery tend "
     "to build features that look impressive but move no real metric."),
    ("Talking to users",
     "The single most reliable input to discovery is regular conversations with real users. Aim for a small number of "
     "interviews every week rather than one big research project once a year. Ask about what people actually did, not "
     "what they say they would do. Watch for the workarounds and spreadsheets people build themselves, because those "
     "are signals of unmet needs you can turn into product opportunities."),
    ("Defining the real problem",
     "The Jobs To Be Done idea says people hire a product to make progress in a situation. Describe the job in the "
     "user's terms, not the feature's terms. For example, the job is not 'use our dashboard'; the job is 'know on "
     "Monday morning whether last week went well'. Framing the problem this way keeps the team focused on the outcome "
     "and open to more than one possible solution."),
    ("Prioritisation: value versus effort",
     "The simplest prioritisation tool is a two-by-two of value against effort. High-value, low-effort work is done "
     "first; low-value, high-effort work is dropped. It is fast and good for a rough first pass, but it hides "
     "assumptions, so use it to start a discussion rather than to end one."),
    ("The RICE framework",
     "RICE scores each idea on Reach, Impact, Confidence, and Effort. Reach is how many users are affected in a period. "
     "Impact is how much it moves the goal per user. Confidence is how sure you are, expressed as a percentage. Effort "
     "is the person-time required. The score is Reach times Impact times Confidence, divided by Effort. RICE is useful "
     "because it forces you to state your confidence out loud instead of hiding it."),
    ("The Kano model",
     "The Kano model sorts features into three kinds. Basic expectations cause anger when missing but no delight when "
     "present, such as a login that works. Performance features are liked more the more you have of them, such as "
     "speed. Delighters are unexpected pleasers that create loyalty. A healthy release covers the basics first, then "
     "invests in a few delighters, rather than adding performance features nobody asked for."),
    ("MoSCoW",
     "MoSCoW splits scope into Must have, Should have, Could have, and Won't have this time. It is most useful for "
     "scoping a specific release under a deadline, because naming the explicit 'won't have' list is what actually "
     "protects the timeline. Without a 'won't have' list, scope quietly grows until the date slips."),
    ("Building a roadmap",
     "A roadmap is a statement of intent, not a delivery contract. Prefer a roadmap organised around problems and "
     "outcomes for the next quarter rather than a dated list of features for the next year. Group work into now, next, "
     "and later. This keeps you honest that far-away items are guesses and gives you room to change course as you learn."),
    ("Common prioritisation mistakes",
     "The most common mistake is prioritising the loudest request instead of the most valuable one. The second is "
     "treating every framework score as a fact rather than an estimate. The third is never revisiting the list, so "
     "stale priorities drive the roadmap for months. Re-score at a regular cadence and treat the numbers as a "
     "conversation starter."),
]

metrics = [
    ("The North Star metric",
     "A North Star metric is the single number that best captures the value your product delivers to users. Good ones "
     "measure customer value, not vanity, such as weekly active teams for a collaboration tool rather than total "
     "signups. The North Star aligns the whole team, because every project can be asked one question: does this move "
     "the North Star, and if not, why are we doing it."),
    ("Pirate metrics (AARRR)",
     "AARRR breaks the user journey into five stages: Acquisition, Activation, Retention, Referral, and Revenue. "
     "Acquisition is how people find you. Activation is the first moment they feel value. Retention is whether they "
     "come back. Referral is whether they tell others. Revenue is whether they pay. Most teams over-invest in "
     "acquisition and under-invest in activation and retention, which is where growth actually compounds."),
    ("Leading versus lagging indicators",
     "A lagging indicator, such as monthly revenue, tells you what already happened but is slow to move. A leading "
     "indicator, such as the number of new users who complete setup in their first session, predicts the lagging "
     "number and moves quickly. After a launch, watch leading indicators first, because they tell you within days "
     "whether the lagging results will follow."),
    ("Defining a minimum viable product",
     "A minimum viable product is the smallest thing you can build to learn whether the idea works. The emphasis is on "
     "learning, not on being small for its own sake. A good MVP tests the riskiest assumption directly. If the risk is "
     "'will people pay', a landing page with a price can be a better MVP than a half-built app."),
    ("Go-to-market and launch checklist",
     "A launch is not just shipping code. Before launch, agree the goal and the metric that defines success, prepare "
     "support and documentation, brief the sales and marketing teams, and decide the rollout plan. A staged rollout to "
     "a small percentage of users first lets you catch problems before everyone sees them. Always know in advance what "
     "number would make you roll the launch back."),
    ("A/B testing and experimentation",
     "An A/B test shows one version to one group and another version to a comparable group, then compares a chosen "
     "metric. It is the cleanest way to know whether a change actually caused an improvement rather than coinciding "
     "with one. Decide the metric and the sample size before you start, and let the test run its full course, because "
     "stopping early the moment results look good is how teams fool themselves."),
    ("Measuring launch success",
     "Judge a launch against the goal you set before it, not against a number you pick afterwards to look good. Combine "
     "a leading indicator for early signal, an activation measure to see if new users reach value, and a retention "
     "measure a few weeks later to see if the value lasts. A launch that spikes signups but shows no retention has not "
     "succeeded; it has only borrowed attention."),
    ("Why retention matters most",
     "Retention is the truest test of product value, because it measures whether people come back on their own. "
     "Acquisition can be bought, but retention has to be earned. A product with strong retention grows even with modest "
     "acquisition, since existing users stay and refer others, while a product with weak retention leaks users as fast "
     "as it adds them, no matter how good the launch looked on day one."),
]

if __name__ == "__main__":
    build("docs/product_discovery.pdf",
          "Product Discovery and Prioritisation: A Practical Guide", discovery)
    build("docs/product_metrics_launch.pdf",
          "Product Metrics, MVP and Launch: A Practical Guide", metrics)