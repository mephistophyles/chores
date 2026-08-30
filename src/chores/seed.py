"""Default chore config, applied once per household.

Generic household chores only — no personal data, and every one of them is
editable in the app afterwards. Seeding is idempotent: a household that
already has categories is left alone, including one that has deleted them all.
"""

DEFAULT_CONFIG = [
    (
        "Daily",
        "daily",
        [
            "Feed kids (breakfast, lunch, dinner)",
            "Wash dishes / load dishwasher after each meal",
            "Wipe kitchen counters & dining table",
            "Sweep kitchen / dining floors",
            "Feed pets, refresh all water bowls",
            "Scoop litter boxes (evening)",
            "Quick yard poop-scoop",
            "Dog bathroom breaks (morning, midday, evening)",
            "Tidy kids' toys into designated bin",
            "Kids' bath / shower + teeth routine",
            "Run dishwasher (overnight) & empty in morning",
            "One load laundry - wash / dry / fold / away",
        ],
    ),
    (
        "Weekly",
        "weekly",
        [
            "Deep-clean sink & garbage disposal",
            "Wipe fridge shelves / handles & microwave inside and out",
            "Take out trash & recycling",
            "Plan next week's meals + create grocery list",
            "Do the big grocery shop",
            "Scrub toilets, sinks, showers / tubs",
            "Wipe mirrors & counters",
            "Wash bath mats & towels",
            "Change all bedsheets",
            "Dust surfaces, shelves, baseboards, sills",
            "Vacuum entire house (especially carpets / rugs)",
            "Wash pet food bowls",
            "Brush all pets thoroughly",
            "Dump & wash litter boxes, refill fresh",
            "Wash pet bedding",
            "Wash delicates / hand-wash items",
            "Sort & put away accumulated clean laundry",
            "Mow lawn & trim edges",
            "Water plants / garden",
            "Sweep porch, entryway, driveway / walkways",
            "Clean outdoor kennel / run area",
        ],
    ),
    (
        "Monthly",
        "monthly",
        [
            "Deep-clean oven, stovetop & exhaust fan",
            "Defrost / wipe out freezer",
            "Clean dishwasher filter & washing machine drum",
            "Vacuum refrigerator coils",
            "Wash windows / glass doors",
            "Rotate / swap seasonal kids' clothes",
            "Check pet supplies (flea and tick meds, food, litter)",
            "Clean car seats / stroller fabric",
            "Declutter one zone (toys, pantry, or garage)",
        ],
    ),
    (
        "Seasonal / As-Needed",
        "none",
        [
            "Grooming appointment for the dog (or at-home nails and ears)",
            "Wash curtains, rugs, or couch covers",
            "Clean gutters / check HVAC filters",
            "Power-wash patio or deck",
        ],
    ),
]


def seed_if_empty(conn, household_id: str, actor: str = "system") -> bool:
    """Insert the default config when this household has none. Returns True if it did."""
    with conn.cursor() as cur:
        # The RLS policies read this setting; seeding must supply it like any request.
        cur.execute("SELECT set_config('app.household_id', %s, false)", (household_id,))
        cur.execute(
            "SELECT 1 FROM chore_categories WHERE household_id = %s LIMIT 1",
            (household_id,),
        )
        if cur.fetchone():
            return False

        for cat_position, (name, cycle, chores) in enumerate(DEFAULT_CONFIG):
            cur.execute(
                "INSERT INTO chore_categories"
                " (household_id, name, cycle, position, created_by)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (household_id, name, cycle, cat_position, actor),
            )
            category_id = cur.fetchone()["id"]
            for position, text in enumerate(chores):
                cur.execute(
                    "INSERT INTO chores"
                    " (household_id, category_id, text, position, created_by)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (household_id, category_id, text, position, actor),
                )
    return True
