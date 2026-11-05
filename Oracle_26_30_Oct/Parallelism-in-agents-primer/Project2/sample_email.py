"""The email each judge classifies.

EMAILS[0] borderline promo, [1] clearly spam, [2] clearly not spam,
[3] the ambiguous one built to SPLIT the judges — half genuine client note,
half sneaky promotion. The demo runs on [3] so the vote actually gets divided.
Change the index in EMAIL below to try the others.
"""

EMAILS = [
    # 0 — borderline: promotional, but the kind of mail a real service sends
    """Hi there! Your free trial ends in 3 days. Upgrade now and get 40% off your
    first year — this offer is only available for the next 72 hours. Click here to
    claim it before it expires!""",

    # 1 — clearly spam
    """CONGRATULATIONS!!! You have WON a $1,000,000 lottery you never entered.
    Send your bank details NOW to claim your prize before midnight!!!""",

    # 2 — clearly not spam
    """Hi Priya, sharing the notes from today's project sync. Action items are at
    the bottom. Let me know if I missed anything before I send it to the team.""",

    # 3 — ambiguous on purpose: a real client follow-up wrapped around a promo hook
    """Hey Chiru! Great chatting yesterday — really enjoyed geeking out about your
    training setup. As promised, I've attached the revised proposal (v2, with the
    timeline you asked for). Oh, and because you're basically our favourite client
    now, here's a cheeky 25% loyalty discount: code TARKA25, good till Friday only.
    No pressure at all — grab it before my manager notices I sent it. Talk soon!""",
]

EMAIL = EMAILS[3]  # runs on the split-vote email — change the index to try others