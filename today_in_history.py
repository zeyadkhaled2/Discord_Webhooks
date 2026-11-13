import json
import os
import random
import urllib.request
from datetime import datetime, timezone

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {
    # Wikimedia asks for a descriptive User-Agent
    "User-Agent": "DiscordTodayInHistory/2.0 (personal friends server)",
    "Content-Type": "application/json",
}
HOW_MANY = 3  # events to post

CARD_THEMES = [
    ("🏛️", "Echoes of the Past", 0xE0A96D),
    ("🧭", "Turning Point", 0x5C9EAD),
    ("✨", "Modern Milestone", 0x9B7EDE),
]


def fetch_events(now):
    url = ("https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/"
           f"{now.month:02d}/{now.day:02d}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("selected", [])


def pick_diverse_events(events, count=HOW_MANY):
    events_sorted = sorted(events, key=lambda e: e.get("year", 0))
    if len(events_sorted) <= count:
        return events_sorted
    # Pick from early, middle, and recent history so every day feels varied
    n = len(events_sorted)
    band = max(1, n // count)
    picks = []
    for i in range(count):
        start = i * band
        end = n if i == count - 1 else (i + 1) * band
        segment = events_sorted[start:end]
        if segment:
            picks.append(random.choice(segment))
    return sorted(picks, key=lambda e: e.get("year", 0))


def primary_page_info(event, fallback_url):
    for page in event.get("pages") or []:
        title = (page.get(" normalizedtitle") or page.get("titles", {}).get("normalized")
                 or page.get("title") or "").replace("_", " ").strip()
        url = (page.get("content_urls", {}).get("desktop", {}).get("page")
               or fallback_url)
        thumb = (page.get("thumbnail") or {}).get("source")
        extract = (page.get("extract") or "").strip()
        if title:
            return title, url, thumb, extract
    return "Wikipedia Archive", fallback_url, None, ""


def main():
    now = datetime.now(timezone.utc)
    events = fetch_events(now)
    if not events:
        print("No events found.")
        return

    picks = pick_diverse_events(events, HOW_MANY)
    date_label = f"{now.strftime('%B')} {now.day}"
    day_wiki_url = f"https://en.wikipedia.org/wiki/{now.strftime('%B')}_{now.day}"

    embeds = []
    for idx, e in enumerate(picks):
        icon, era_label, color = CARD_THEMES[idx % len(CARD_THEMES)]
        year = e.get("year", 0)
        years_ago = now.year - year if year else None
        ago_badge = f"  •  *{years_ago:,} years ago today*" if years_ago and years_ago > 0 else ""

        text = (e.get("text") or "").strip()
        if len(text) > 340:
            text = text[:337].rstrip() + "..."

        page_title, page_url, thumb, extract = primary_page_info(e, day_wiki_url)
        desc = f"> {text}"
        if extract and extract[:60].lower() not in text.lower():
            snippet = extract if len(extract) <= 180 else extract[:177].rstrip() + "..."
            desc += f"\n\n💡 *{snippet}*"
        desc += f"\n\n📖 **[Explore \"{page_title}\" on Wikipedia ↗]({page_url})**"

        embed = {
            "author": {
                "name": f"{icon} {era_label.upper()}  •  {date_label.upper()}",
                "url": day_wiki_url,
            },
            "title": f"📜  {year} — {page_title}",
            "url": page_url,
            "description": f"🗓️ **Year {year}**{ago_badge}\n\n{desc}",
            "color": color,
            "footer": {"text": f"Story {idx + 1} of {len(picks)} • Wikipedia On This Day"},
        }
        if thumb:
            embed["thumbnail"] = {"url": thumb}
        embeds.append(embed)

    body = json.dumps({
        "username": "Time Capsule • On This Day",
        "content": (
            f"## ☕ **Daily Time Capsule — {date_label}**\n"
            f"-# {len(embeds)} handpicked moments across history that happened on this exact date"
        ),
        "embeds": embeds,
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} historical stories.")


if __name__ == "__main__":
    main()
