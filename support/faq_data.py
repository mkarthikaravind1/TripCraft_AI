"""
Help-centre FAQ content. Loaded into the SQL database by migration
0002_seed_faqs and by `python manage.py seed_faqs` (idempotent).
Answers describe only features that exist in this codebase.
"""

FAQS = [
    {
        "question": "What is TripCraft AI?",
        "category": "getting_started",
        "keywords": "about overview purpose what does it do travel planner",
        "answer": (
            "TripCraft AI is a travel-planning website. You enter a destination, dates, budget, number of travellers "
            "and interests, and it creates a day-by-day itinerary using Google Gemini, together with an estimated "
            "budget you can adjust. It plans trips; it does not book anything."
        ),
    },
    {
        "question": "How do I create a travel itinerary?",
        "category": "planning",
        "keywords": "create make generate plan new trip itinerary start form steps",
        "answer": (
            "Select “Plan your trip”, then complete three short steps: where and when (destination and dates), "
            "budget and group (total budget, currency, travellers, transport) and your travel style (interests, pace, "
            "dietary and accessibility needs). Select “Generate my itinerary”. Generation usually takes 15–45 seconds, "
            "after which your trip dashboard opens."
        ),
    },
    {
        "question": "Do I need an account to use TripCraft AI?",
        "category": "account",
        "keywords": "account register sign up login required anonymous free",
        "answer": (
            "No. You can plan trips without an account — they are kept in your current browser session. If you sign up "
            "(only a username and password are needed) or log in, trips planned in that browser are attached to your "
            "account so you can find them later under “My trips”."
        ),
    },
    {
        "question": "Can I customise my travel budget?",
        "category": "budget",
        "keywords": "customise customize adjust change budget cheaper meals accommodation stay transport contingency save money",
        "answer": (
            "Yes. The “Adjust your budget” panel on the trip dashboard lets you choose cheaper or more premium meal and "
            "accommodation styles, type your own transport and miscellaneous amounts, change the contingency buffer "
            "(0–30%) and preview the savings from trimming paid activities above a chosen price. Totals and charts "
            "update immediately and changes are saved automatically."
        ),
    },
    {
        "question": "How are estimated travel costs calculated?",
        "category": "budget",
        "keywords": "cost costs calculated calculation estimate estimates price prices accurate maths total",
        "answer": (
            "The AI (or the local sample planner) suggests per-person costs for activities and meals and trip-level "
            "estimates for transport, accommodation and extras. TripCraft then does all the arithmetic itself: it "
            "multiplies per-person costs by the number of travellers, applies your meal and stay choices, adds the "
            "contingency buffer and checks the total against your budget. Costs are estimates, not verified prices — "
            "always confirm real prices before booking."
        ),
    },
    {
        "question": "Can I change activities in my itinerary?",
        "category": "planning",
        "keywords": "change edit remove delete restore activity activities complete done mark itinerary",
        "answer": (
            "Yes. On the dashboard you can expand an activity for details, mark it as done, or remove it from your plan. "
            "Removed activities stay visible (struck through) so you can restore them, and the budget updates as you go. "
            "You can also regenerate the whole itinerary, which replaces the current plan."
        ),
    },
    {
        "question": "Does TripCraft AI book hotels or flights?",
        "category": "getting_started",
        "keywords": "book booking hotel hotels flight flights reservation tickets pay payment",
        "answer": (
            "No. TripCraft AI only helps you plan. It does not book hotels, flights or activities and never takes "
            "payments. Use the itinerary and budget as a guide when booking with providers of your choice."
        ),
    },
    {
        "question": "How can I save or print my itinerary?",
        "category": "account",
        "keywords": "save print pdf download export keep itinerary copy",
        "answer": (
            "Trips are saved automatically — in your browser session, or in your account if you are logged in. To print "
            "or create a PDF, select “Print / save PDF” on the trip dashboard and choose “Save as PDF” in your "
            "browser's print dialog. The printout shows every day and the budget breakdown."
        ),
    },
    {
        "question": "Why might AI itinerary generation fail?",
        "category": "troubleshooting",
        "keywords": "ai fail fails failed failing generation error sample itinerary gemini not working TRIPCRAFT_001",
        "answer": (
            "Live AI generation can be unavailable if no Gemini API key is configured, the AI service times out or is "
            "rate-limited, or its response cannot be validated. When that happens TripCraft shows error code "
            "TRIPCRAFT_001 and gives you a clearly labelled sample itinerary instead, so you can keep planning. You can "
            "use “Try live AI again” on the dashboard later."
        ),
    },
    {
        "question": "What should I do if the website shows an error code?",
        "category": "troubleshooting",
        "keywords": "error code codes 400 401 403 404 429 500 503 message problem page",
        "answer": (
            "Each error page explains what happened and what to try next. The help centre lists every supported code "
            "(400, 401, 403, 404, 429, 500, 503 and TRIPCRAFT_001). You can also ask the assistant, for example "
            "“What does error 429 mean?”. If the problem continues, create a support ticket and mention the code."
        ),
    },
    {
        "question": "How do I contact support?",
        "category": "support",
        "keywords": "contact support help ticket human team report problem email",
        "answer": (
            "Ask the assistant first — if it cannot answer, it will offer to create a support ticket. You can also use "
            "the support form at the bottom of the help centre. Each ticket gets a reference such as TC-ABCD2345. An "
            "email address is optional, and TripCraft does not currently send emails automatically."
        ),
    },
    {
        "question": "Is the weather forecast always available?",
        "category": "planning",
        "keywords": "weather forecast temperature rain open-meteo climate",
        "answer": (
            "The trip dashboard shows a daily forecast from Open-Meteo when your travel dates fall within its forecast "
            "window (about the next 16 days) and the destination can be located. For later dates, or if the weather "
            "service is unreachable, TripCraft says so instead of guessing."
        ),
    },
    {
        "question": "Which currencies and trip lengths are supported?",
        "category": "planning",
        "keywords": "currency currencies inr usd eur gbp length days long maximum travellers limit",
        "answer": (
            "You can plan in INR, USD, EUR, GBP, JPY, AUD, CAD, SGD, AED or THB. Trips can be 1–14 days long for 1–20 "
            "travellers, starting today or up to two years ahead. The budget must be realistic for the group and trip "
            "length; the form tells you the minimum if it is too low."
        ),
    },
    {
        "question": "What information does TripCraft AI store about me?",
        "category": "account",
        "keywords": "privacy data personal information stored store gdpr delete",
        "answer": (
            "TripCraft stores your trip preferences and itineraries, support tickets you create, and assistant "
            "conversations and feedback (for improving help answers). Accounts need only a username and password. "
            "You can delete any trip from its dashboard. Please don't share passwords or payment details in the chat."
        ),
    },
]
