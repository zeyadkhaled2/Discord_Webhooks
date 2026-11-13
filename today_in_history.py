import json
import os
import random
import urllib.request
from datetime import datetime, timezone

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {
    # Wikimedia asks for a descriptive User-Agent
    "User-Agent": "DiscordTodayInHistory/3.0 (personal friends server)",
    "Content-Type": "application/json",
}
HOW_MANY = 3  # main featured events


def fetch_events(now):
    url = ("https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/"
           f"{now.month:02d}/{now.day:02d}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r).get("selected", [])


def pick_diverse_events(events, count=HOW_MANY):
    events_sorted = sorted(events, key=lambda e: e.get("year", 0))
    if len(events_sorted) <= count:
        return events_sorted, []
    n = len(events_sorted)
    band = max(1, n // count)
    picks = []
    for i in range(count):
        start = i * band
        end = n if i == count - 1 else (i + 1) * band
        segment = events_sorted[start:end]
        if segment:
            picks.append(random.choice(segment))
    picked_years = {id(p) for p in picks}
    extras = [e for e in events_sorted if id(e) not in picked_years]
    random.shuffle(extras)
    return sorted(picks, key=lambda e: e.get("year", 0)), sorted(extras[:3], key=lambda e: e.get("year", 0))


def primary_page_info(event, fallback_url):
    for page in event.get("pages") or []:
        title = (page.get("normalizedtitle") or page.get("titles", {}).get("normalized")
                 or page.get("title") or "").replace("_", " ").strip()
        url = (page.get("content_urls", {}).get("desktop", {}).get("page")
               or fallback_url)
        thumb = (page.get("thumbnail") or {}).get("source")
        if title:
            return title, url, thumb
    return "Wikipedia Archive", fallback_url, None


def main():
    now = datetime.now(timezone.utc)
    events = fetch_events(now)
    if not events:
        print("No events found.")
        return

    picks, extras = pick_diverse_events(events, HOW_MANY)
    date_label = f"{now.strftime('%B')} {now.day}"
    day_wiki_url = f"https://en.wikipedia.org/wiki/{now.strftime('%B')}_{now.day}"

    sections = [
        "```ansi\n"
        f"\u001b[1;33m⏳ TIME CAPSULE\u001b[0m \u001b[1;36m• {date_label.upper()} IN HISTORY\u001b[0m\n"
        "```"
    ]
    best_thumb = None
    badges = ["🟧", "🟦", "🟪"]

    for idx, e in enumerate(picks):
        badge = badges[idx % len(badges)]
        year = e.get("year", 0)
        years_ago = now.year - year if year else None
        ago_tag = f"`{years_ago:,} yrs ago`" if years_ago and years_ago > 0 else ""

        text = (e.get("text") or "").strip()
        if len(text) > 240:
            text = text[:237].rstrip() + "..."

        page_title, page_url, thumb = primary_page_info(e, day_wiki_url)
        if thumb and not best_thumb:
            best_thumb = thumb

        sections.append(
            f"### {badge} [{year} — {page_title}]({page_url}) {ago_tag}\n"
            f"> {text}\n"
            f"-# 👉 [Read more about **{page_title}** ↗]({page_url})"
        )

    if extras:
        extra_lines = []
        for ex in extras:
            yr = ex.get("year", 0)
            txt = (ex.get("text") or "").strip()
            if len(txt) > 120:
                txt = txt[:117].rstrip() + "..."
            extra_lines.append(f"• **`{yr}`** — {txt}")
        spoiler = "\n".join(extra_lines)
        sections.append(
            f"🔽 **Bonus Historical Moments *(click box to expand)*:**\n||{spoiler}||"
        )

    sections.append(f"👉 **[📖 Explore All Events for {date_label} on Wikipedia ↗]({day_wiki_url})**")

    embed = {
        "author": {
            "name": f"🏛️ ON THIS DAY  •  {date_label.upper()}",
            "url": day_wiki_url,
        },
        "description": "\n\n".join(sections)[:4000],
        "color": 0xFFB800,
        "footer": {"text": "🟨 Daily Time Capsule • Click any blue title to read more"},
    }
    if best_thumb:
        embed["thumbnail"] = {"url": best_thumb}

    body = json.dumps({
        "username": "Time Capsule • On This Day",
        "content": (
            f"### ☕ **Daily Time Capsule — {date_label}**\n"
            f"-# Remarkable moments across history that happened on this exact date"
        ),
        "embeds": [embed],
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print("Posted single rich Time Capsule card.")


if __name__ == "__main__":
    main()
