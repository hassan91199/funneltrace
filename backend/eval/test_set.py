"""The 10 locked eval leads (brief: a spread of hot/warm/cold plus at least one
same-person-two-channels case, written before any scoring code).

Scenario: inbound leads for a small home-services company (HVAC, plumbing,
remodels). The 10 events are an ordered stream; the run feeds them in id order
against an empty database, so dedup is graded against what came before.

Category definitions the scorer is graded against:
  hot  - clear intent to buy now (urgent need, near-term timeline, budget or a
         decision date), ready for same-day human contact.
  warm - real interest but no urgency: a genuine need with a longer timeline or
         still gathering information.
  cold - not a buyer: browsing with no intent, or a vendor soliciting us.

Graded per event: `expected_category`, dedup (`person` groups events that are
the same human; `expect_new_lead` says whether it must create a new record),
draft relevance (`draft_must_address`: points a relevant draft must cover, judged
by a rubric, not string match), and the CRM write (`expected_crm`: create vs
update, and the HubSpot lifecycle stage the category maps to: hot ->
salesqualifiedlead, warm -> marketingqualifiedlead, cold -> lead).

Payload shapes are the raw channel payloads; the intake task may adapt the exact
webhook field names, but the content and expected outcomes stay as locked here.
Phone numbers are fictional (555 range / invalid). Nothing here talks to a model
or a database.
"""

CATEGORIES = ("hot", "warm", "cold")

TEST_SET = [
    {
        "id": 1,
        "channel": "web_form",
        "person": "sarah-mitchell",
        "payload": {
            "name": "Sarah Mitchell",
            "email": "sarah.mitchell@gmail.com",
            "phone": "+1 (415) 555-0142",
            "message": (
                "Our furnace died last night and it's freezing. I need a replacement quote "
                "this week. Budget is approved up to $9k."
            ),
        },
        "expected_category": "hot",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "salesqualifiedlead"},
        "draft_must_address": [
            "acknowledges the furnace outage and the urgency",
            "offers a fast next step (call or visit this week)",
            "does not quote a price",
        ],
        "notes": "Urgent need + stated budget + deadline. First half of the same-person case.",
    },
    {
        "id": 2,
        "channel": "whatsapp",
        "person": "sarah-mitchell",
        "payload": {
            "from": "14155550142",
            "profile_name": "Sarah M",
            "text": (
                "Hi, I sent a form earlier. Can someone call me today? The furnace is out "
                "and the house is cold."
            ),
        },
        "expected_category": "hot",
        "expect_new_lead": False,
        "expected_crm": {"action": "update", "lifecycle_stage": "salesqualifiedlead"},
        "draft_must_address": [
            "references her earlier form request (knows she already reached out)",
            "commits to a same-day call back",
        ],
        "notes": (
            "Same person via the other channel: phone matches #1 (different formatting), "
            "name 'Sarah M' fuzzy-matches. Must merge into one lead, not duplicate."
        ),
    },
    {
        "id": 3,
        "channel": "web_form",
        "person": "daniel-okafor",
        "payload": {
            "name": "Daniel Okafor",
            "email": "d.okafor@fastmail.com",
            "phone": "+1 650 555 0177",
            "message": (
                "Planning a kitchen remodel in about three months. Would like a ballpark "
                "and to understand how your process works."
            ),
        },
        "expected_category": "warm",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "marketingqualifiedlead"},
        "draft_must_address": [
            "answers the process question at a high level",
            "offers a consultation without pushing urgency",
        ],
        "notes": "Genuine need, three-month timeline, still gathering information.",
    },
    {
        "id": 4,
        "channel": "whatsapp",
        "person": "priya-sharma",
        "payload": {
            "from": "923005550188",
            "profile_name": "Priya",
            "text": "hi how much for an AC tune up?",
        },
        "expected_category": "warm",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "marketingqualifiedlead"},
        "draft_must_address": [
            "responds to the tune-up pricing question without inventing a price",
            "asks one or two details to give an accurate quote",
        ],
        "notes": "Short, vague, but a real service inquiry; no urgency signal.",
    },
    {
        "id": 5,
        "channel": "web_form",
        "person": "mike-torres",
        "payload": {
            "name": "Mike Torres",
            "email": "mtorres88@yahoo.com",
            "phone": "",
            "message": "Just browsing, saw your ad. Not looking to buy anything right now.",
        },
        "expected_category": "cold",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "lead"},
        "draft_must_address": [
            "short and low-pressure",
            "leaves the door open without a hard sell",
        ],
        "notes": "Explicitly says no intent. Empty phone must be handled by intake and dedup.",
    },
    {
        "id": 6,
        "channel": "web_form",
        "person": "jason-lee",
        "payload": {
            "name": "Jason Lee",
            "email": "jason.lee@example.com",
            "phone": "+1 305 555 0110",
            "message": (
                "We can get your company onto page 1 of Google in 30 days. Reply for a free audit."
            ),
        },
        "expected_category": "cold",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "lead"},
        "draft_must_address": [
            "politely declines or states no interest",
            "does not engage with the sales pitch or commit to anything",
        ],
        "notes": "A vendor soliciting us, not a buyer. The reasoning should say so.",
    },
    {
        "id": 7,
        "channel": "whatsapp",
        "person": "ahmed-raza",
        "payload": {
            "from": "447700900123",
            "profile_name": "Ahmed Raza",
            "text": (
                "Water pipe burst in my basement, need a plumber ASAP. I'll pay the "
                "emergency rate, please come now."
            ),
        },
        "expected_category": "hot",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "salesqualifiedlead"},
        "draft_must_address": [
            "treats it as an emergency and replies immediately",
            "gives safety advice such as shutting off the main water valve",
            "confirms someone will call or dispatch right away",
        ],
        "notes": "Emergency with stated willingness to pay. Hot by any reading.",
    },
    {
        "id": 8,
        "channel": "web_form",
        "person": "sarah-mitchel-gutters",
        "near_miss_of": 1,
        "payload": {
            "name": "Sarah Mitchel",
            "email": "smitchel@outlook.com",
            "phone": "+1 (212) 555-0199",
            "message": "Looking for a quote on gutter cleaning sometime next month.",
        },
        "expected_category": "warm",
        "expect_new_lead": True,
        "expected_crm": {"action": "create", "lifecycle_stage": "marketingqualifiedlead"},
        "draft_must_address": [
            "responds about gutter cleaning, not a furnace",
            "asks about house size or access to quote",
        ],
        "notes": (
            "Near-miss: name differs from #1 by one letter but email and phone are "
            "different. A different person; must NOT merge."
        ),
    },
    {
        "id": 9,
        "channel": "whatsapp",
        "person": "daniel-okafor",
        "payload": {
            "from": "16505550177",
            "profile_name": "Dan Okafor",
            "text": (
                "Following up on the kitchen remodel. We have quotes from two other "
                "contractors and decide Friday. Can you come out Thursday?"
            ),
        },
        "expected_category": "hot",
        "expect_new_lead": False,
        "expected_crm": {"action": "update", "lifecycle_stage": "salesqualifiedlead"},
        "draft_must_address": [
            "references the kitchen remodel and his Friday decision",
            "confirms or proposes a Thursday visit",
        ],
        "notes": (
            "Same person as #3 on the other channel (phone matches, 'Dan' fuzzy-matches "
            "'Daniel'). Re-scoring with the new message upgrades warm to hot; the "
            "scoring history keeps both."
        ),
    },
    {
        "id": 10,
        "channel": "web_form",
        "person": "priya-sharma",
        "payload": {
            "name": "Priya Sharma",
            "email": "priya.sharma@example.com",
            "phone": "+92 300 5550188",
            "message": (
                "Following up on WhatsApp. Looking for a tune-up for our central AC "
                "before summer, no rush."
            ),
        },
        "expected_category": "warm",
        "expect_new_lead": False,
        "expected_crm": {"action": "update", "lifecycle_stage": "marketingqualifiedlead"},
        "draft_must_address": [
            "references her earlier WhatsApp message",
            "proposes scheduling the tune-up before summer",
        ],
        "notes": (
            "Same person as #4 on the other channel, only the phone matches (spaced vs "
            "unspaced format). Stays warm, and gains an email on the merged record."
        ),
    },
]
