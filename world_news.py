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
HEADERS = {"User-Agent": "Mozilla/5.0 (DiscordNewsDigest/3.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}

# (name, badge_emoji, ansi_color, rss url, site_url, embed color, featured_count, extra_count)
FEEDS = [
    ("BBC World News", "🟥", "\u001b[1;31m", "https://feeds.bbci.co.uk/news/world/rss.xml", "https://www.bbc.com/news/world", 0xFF1E56, 3, 3),
    ("Al Jazeera English", "🟧", "\u001b[1;33m", "https://www.aljazeera.com/xml/rss/all.xml", "https://www.aljazeera.com", 0xFFB800, 3, 3),
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


def build_feed_embed(name, badge, ansi_color, site_url, color, items, featured_count):
    lead = items[0]
    lead_time = f"  •  <t:{lead['pub_ts']}:R>" if lead.get("pub_ts") else ""
    lead_desc = lead.get("desc") or ""
    if len(lead_desc) > 210:
        lead_desc = lead_desc[:207].rstrip() + "..."

    sections = [
        f"```ansi\n{ansi_color}🌍 {name.upper()}\u001b[0m \u001b[1;36m• BREAKING & TOP STORIES\u001b[0m\n```",
        f"# 🚨 [{lead['title'][:180]}]({lead['link']})",
    ]
    if lead_desc:
        sections.append(f"> {lead_desc}")
    sections.append(f"-# 🕒 Published{lead_time}  •  👉 [**Read Lead Story ↗**]({lead['link']})")

    featured = items[1:featured_count]
    if featured:
        for idx, entry in enumerate(featured, 2):
            rel = f" `({idx})`"
            time_tag = f" • <t:{entry['pub_ts']}:R>" if entry.get("pub_ts") else ""
            line = f"## 🔹 [{entry['title'][:160]}]({entry['link']}){rel}"
            if entry.get("desc"):
                short = entry["desc"]
                if len(short) > 130:
                    short = short[:127].rstrip() + "..."
                line += f"\n> {short}"
            line += f"\n-# 🕒 Updated{time_tag}  •  [Read More ↗]({entry['link']})"
            sections.append(line)

    extras = items[featured_count:]
    if extras:
        spoiler_lines = []
        for idx, ex in enumerate(extras, featured_count + 1):
            spoiler_lines.append(f"**{idx}.** [{ex['title'][:120]}]({ex['link']})")
        sections.append(
            "### ➕ More Headlines *(click box to expand)*\n"
            + "||" + "\n".join(spoiler_lines) + "||\n"
            + f"## 👉 [📰 Browse All {name} Headlines ↗]({site_url})"
        )

    embed = {
        "author": {
            "name": f"{badge} {name.upper()}  •  WORLD DESK",
            "url": site_url,
        },
        "description": "\n\n".join(sections)[:4000],
        "color": color,
        "footer": {"text": f"{badge} {name} • Major stories in large font • Click spoiler for more"},
    }
    if lead.get("thumb"):
        embed["thumbnail"] = {"url": lead["thumb"]}
    return embed


def main():
    embeds = []
    for name, badge, ansi_color, url, site_url, color, feat_n, extra_n in FEEDS:
        try:
            items = fetch_items(url, feat_n + extra_n)
        except Exception as e:
            print(f"Skipping {name}: {e}")
            continue
        if not items:
            continue
        embeds.append(build_feed_embed(name, badge, ansi_color, site_url, color, items, feat_n))

    if not embeds:
        print("Nothing to post.")
        return

    now = datetime.now(timezone.utc)
    today = now.strftime("%A, %d %B %Y")
    now_ts = int(now.timestamp())
    body = json.dumps({
        "username": "Morning Briefing • World Desk",
        "content": (
            f"# ☕ **World News Briefing — {today}**\n"
            f"-# Major headlines in large print • Updated <t:{now_ts}:R>"
        ),
        "embeds": embeds,
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=JSON_HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} feed(s).")


if __name__ == "__main__":
    main()
