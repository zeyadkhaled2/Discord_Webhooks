import html
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
 
WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {"User-Agent": "Mozilla/5.0 (DiscordNewsDigest/1.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
 
# Add or remove feeds here:
# (name, rss url, embed color, headlines to show, show short description?)
FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", 0xBB1919, 6, True),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", 0xFA9000, 5, True),
    ("The Guardian World", "https://www.theguardian.com/world/rss", 0x052962, 5, True),
]
 
 
def clean(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return html.unescape(text).strip()
 
 
def fetch_items(url, limit):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for item in root.iter("item"):
        title = clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        desc = clean(item.findtext("description"))
        if title and link:
            items.append((title, link, desc))
    return items[:limit]
 
 
def format_item(title, link, desc, show_desc):
    # Clicking the bold title opens the full article
    line = f"**[{title[:200]}]({link})**"
    if show_desc and desc:
        if len(desc) > 220:
            desc = desc[:217].rstrip() + "..."
        line += f"\n{desc}"
    return line
 
 
def main():
    embeds = []
    for name, url, color, limit, show_desc in FEEDS:
        try:
            items = fetch_items(url, limit)
        except Exception as e:  # one broken feed shouldn't stop the others
            print(f"Skipping {name}: {e}")
            continue
        if not items:
            continue
        sep = "\n\n" if show_desc else "\n"
        text = sep.join(format_item(t, l, d, show_desc) for t, l, d in items)
        embeds.append({
            "title": f"🌍 {name}",
            "description": text[:4000],
            "color": color,
        })
 
    if not embeds:
        print("Nothing to post.")
        return
 
    body = json.dumps({
        "username": "World News",
        "content": "📰 **Today's world headlines**",
        "embeds": embeds,
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=JSON_HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} feed(s).")
 
 
if __name__ == "__main__":
    main()
 
