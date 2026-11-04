import json
import os
import urllib.request
import xml.etree.ElementTree as ET
 
WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
HEADERS = {"User-Agent": "Mozilla/5.0 (DiscordNewsDigest/1.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
HEADLINES_PER_FEED = 5
 
# Add or remove feeds here: (name, rss url, embed color)
FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", 0xBB1919),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", 0xFA9000),
    ("The Guardian World", "https://www.theguardian.com/world/rss", 0x052962),
]
 
 
def fetch_items(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title and link:
            items.append((title, link))
    return items[:HEADLINES_PER_FEED]
 
 
def main():
    embeds = []
    for name, url, color in FEEDS:
        try:
            items = fetch_items(url)
        except Exception as e:  # one broken feed shouldn't stop the others
            print(f"Skipping {name}: {e}")
            continue
        if not items:
            continue
        lines = [f"• [{t[:200]}]({l})" for t, l in items]
        embeds.append({
            "title": f"🌍 {name}",
            "description": "\n".join(lines),
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
