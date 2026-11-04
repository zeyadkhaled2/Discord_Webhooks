import json
import os
import random
import urllib.request
from datetime import datetime, timezone

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {
    # Wikimedia asks for a descriptive User-Agent
    "User-Agent": "DiscordTodayInHistory/1.0 (personal friends server)",
    "Content-Type": "application/json",
}
HOW_MANY = 3  # events to post


def fetch_events(now):
    url = ("https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/"
           f"{now.month:02d}/{now.day:02d}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("selected", [])


def find_image(events):
    for e in events:
        for page in e.get("pages", []):
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
    return None


def main():
    now = datetime.now(timezone.utc)
    events = fetch_events(now)
    if not events:
        print("No events found.")
        return

    picks = random.sample(events, min(HOW_MANY, len(events)))
    picks.sort(key=lambda e: e.get("year", 0))

    lines = []
    for e in picks:
        text = e["text"]
        if len(text) > 250:
            text = text[:247] + "..."
        lines.append(f"**{e['year']}** — {text}")

    date_label = f"{now.strftime('%B')} {now.day}"
    embed = {
        "title": f"📅 On this day — {date_label}",
        "url": f"https://en.wikipedia.org/wiki/{now.strftime('%B')}_{now.day}",
        "description": "\n\n".join(lines),
        "color": 0x3366CC,
        "footer": {"text": "Source: Wikipedia"},
    }
    image = find_image(picks)
    if image:
        embed["thumbnail"] = {"url": image}

    body = json.dumps({"username": "Today in History", "embeds": [embed]}).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print("Posted.")


if __name__ == "__main__":
    main()
