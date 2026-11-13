import email.utils
import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Uses DISCORD_WEBHOOK_URL_3 if set, otherwise falls back to DISCORD_WEBHOOK_URL
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL_3") or os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {"User-Agent": "Mozilla/5.0 (DiscordNewsDigest/2.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}

# Add or remove feeds here:
# (name, badge_emoji, rss url, site_url, embed color, headlines to show, show short description?)
FEEDS = [
    ("BBC World News", "🔴", "https://feeds.bbci.co.uk/news/world/rss.xml", "https://www.bbc.com/news/world", 0xBB1919, 5, True),
    ("Al Jazeera English", "🟠", "https://www.aljazeera.com/xml/rss/all.xml", "https://www.aljazeera.com", 0xFA9000, 5, True),
]

MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text


def parse_pub_ts(pub_date):
    if not pub_date:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(pub_date.strip())
        return int(dt.timestamp())
    except Exception:
        return None


def find_media_thumb(item):
    for tag in (f"{MEDIA_NS}thumbnail", f"{MEDIA_NS}content", "enclosure"):
        el = item.find(tag)
        if el is not None and el.get("url"):
            return el.get("url")
    return None


def fetch_items(url, limit):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        desc = clean(item.findtext("description"))
        pub_ts = parse_pub_ts(item.findtext("pubDate"))
        thumb = find_media_thumb(item)
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "desc": desc,
                "pub_ts": pub_ts,
                "thumb": thumb,
            })
    return items[:limit]


def build_feed_embed(name, badge, site_url, color, items, show_desc):
    lead = items[0]
    lead_time = f"  •  <t:{lead['pub_ts']}:R>" if lead.get("pub_ts") else ""
    lead_desc = lead.get("desc") or ""
    if len(lead_desc) > 220:
        lead_desc = lead_desc[:217].rstrip() + "..."

    sections = [f"### 📌 [{lead['title'][:190]}]({lead['link']})"]
    if lead_desc:
        sections.append(f"> {lead_desc}")
    if lead_time:
        sections.append(f"-# 🕒 Published{lead_time}")

    if len(items) > 1:
        sections.append("-# ──────────────────────────────")
        for idx, entry in enumerate(items[1:], 2):
            rel = f" *(<t:{entry['pub_ts']}:R>)*" if entry.get("pub_ts") else ""
            line = f"**{idx}.** [**{entry['title'][:170]}**]({entry['link']}){rel}"
            if show_desc and entry.get("desc"):
                short = entry["desc"]
                if len(short) > 125:
                    short = short[:122].rstrip() + "..."
                line += f"\n-# ↳ {short}"
            sections.append(line)

    embed = {
        "author": {
            "name": f"{badge} {name.upper()}  •  TOP DISPATCH",
            "url": site_url,
        },
        "description": "\n\n".join(sections)[:4000],
        "color": color,
        "footer": {"text": f"{name} • Click any headline to read the full story"},
    }
    if lead.get("thumb"):
        embed["thumbnail"] = {"url": lead["thumb"]}
    return embed


def main():
    embeds = []
    for name, badge, url, site_url, color, limit, show_desc in FEEDS:
        try:
            items = fetch_items(url, limit)
        except Exception as e:  # one broken feed shouldn't stop the others
            print(f"Skipping {name}: {e}")
            continue
        if not items:
            continue
        embeds.append(build_feed_embed(name, badge, site_url, color, items, show_desc))

    if not embeds:
        print("Nothing to post.")
        return

    now = datetime.now(timezone.utc)
    today = now.strftime("%A, %d %B %Y")
    now_ts = int(now.timestamp())
    body = json.dumps({
        "username": "Morning Briefing • World Desk",
        "content": (
            f"## ☕ **World News Briefing — {today}**\n"
            f"-# Curated international headlines • Updated <t:{now_ts}:R>"
        ),
        "embeds": embeds,
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=JSON_HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} feed(s).")


if __name__ == "__main__":
    main()
