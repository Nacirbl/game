#!/usr/bin/env python3
"""
One-off script: populate questions_db.json from the seed files.

- Merges question_seed_couples.py / question_seed_daily.py / question_seed_fun.py
  into the existing database (existing questions are kept; md5 id dedup applies).
- Registers category metadata (name + emoji) for new categories.
- Assigns category-level tags and a difficulty mix.

Run from the repo root:  python3 populate_question_db.py
"""
from question_database import QuestionDatabase
from question_seed_couples import SEED as SEED_COUPLES
from question_seed_daily import SEED as SEED_DAILY
from question_seed_fun import SEED as SEED_FUN

# Metadata for every category we want exposed on the home page.
# Existing ones keep their current name/emoji unless overridden.
CATEGORY_META = {
    "general":     {"name": "General",           "emoji": "🎯"},
    "couples":     {"name": "Couples & Romance", "emoji": "💑"},
    "date-night":  {"name": "Date Night",        "emoji": "🌹"},
    "deep-talks":  {"name": "Deep Talks",        "emoji": "💬"},
    "future-us":   {"name": "Future Plans",      "emoji": "💍"},
    "home-living": {"name": "Home & Living",     "emoji": "🏡"},
    "silly-fun":   {"name": "Silly & Fun",       "emoji": "🎲"},
    "food-drink":  {"name": "Food & Drink",      "emoji": "🍔"},
    "travel":      {"name": "Travel & Places",   "emoji": "✈️"},
    "lifestyle":   {"name": "Lifestyle",         "emoji": "🏠"},
    "entertainment": {"name": "Entertainment",   "emoji": "🎬"},
    "technology":  {"name": "Technology",        "emoji": "📱"},
    "sports":      {"name": "Sports & Fitness",  "emoji": "⚽"},
    "fashion":     {"name": "Fashion & Style",   "emoji": "👗"},
    "nature":      {"name": "Nature & Animals",  "emoji": "🌳"},
    "work":        {"name": "Work & Career",     "emoji": "💼"},
}

# Base tags applied to every question in a category.
CATEGORY_TAGS = {
    "couples":     ["couples", "relationship", "romance"],
    "date-night":  ["couples", "dating", "activities"],
    "deep-talks":  ["conversation", "values", "deep"],
    "future-us":   ["couples", "future", "planning"],
    "home-living": ["home", "domestic", "everyday"],
    "silly-fun":   ["funny", "lighthearted", "would-you-rather"],
    "general":     ["general", "mixed"],
    "food-drink":  ["food", "drinks", "taste"],
    "travel":      ["travel", "destinations", "adventure"],
    "lifestyle":   ["lifestyle", "habits", "daily"],
    "entertainment": ["movies", "music", "pop-culture"],
    "technology":  ["tech", "gadgets", "digital"],
    "sports":      ["sports", "fitness", "competition"],
    "fashion":     ["fashion", "style", "clothes"],
    "nature":      ["nature", "animals", "outdoors"],
    "work":        ["work", "career", "office"],
}

DIFFICULTIES = ["easy", "medium", "hard"]

def main():
    db = QuestionDatabase('questions_db.json')
    before = len(db.questions)

    seeds = {**SEED_COUPLES, **SEED_DAILY, **SEED_FUN}

    # Register/refresh category metadata
    for cat_id, meta in CATEGORY_META.items():
        if cat_id not in db.categories:
            db.categories[cat_id] = {
                "name": meta["name"], "emoji": meta["emoji"], "question_count": 0
            }
        else:
            db.categories[cat_id]["name"] = meta["name"]
            db.categories[cat_id]["emoji"] = meta["emoji"]

    added = skipped = 0
    for cat_id, questions in seeds.items():
        base_tags = CATEGORY_TAGS.get(cat_id, [cat_id])
        for i, (prompt, option1, option2) in enumerate(questions):
            existed = db.add_question(
                prompt=prompt,
                option1=option1,
                option2=option2,
                category=cat_id,
                tags=base_tags,
                difficulty=DIFFICULTIES[i % len(DIFFICULTIES)]
            )
            # add_question returns early for duplicates; approximate detection:
            added += 1

    db.save_database()

    after = len(db.questions)
    print(f"questions before: {before}")
    print(f"seed rows:         {added}")
    print(f"questions after:  {after}  (+{after - before})")

    # Per-category census
    print("\nper category:")
    for cat_id, cat_data in db.categories.items():
        count = len(db.category_index.get(cat_id, []))
        print(f"  {cat_data['emoji']} {cat_id:14} {count}")

    # Near-dupe check: same normalized content appearing twice
    import re
    def norm(q):
        key = f"{q['prompt']}|{q['option1']}|{q['option2']}".lower()
        return re.sub(r"[^a-z0-9|]", "", key)
    seen, dupes = set(), []
    for q in db.questions:
        k = norm(q)
        if k in seen:
            dupes.append(q['prompt'])
        seen.add(k)
    print(f"\nnear-duplicate prompts: {len(dupes)}")
    for d in dupes[:10]:
        print("  dupe:", d)

if __name__ == "__main__":
    main()
