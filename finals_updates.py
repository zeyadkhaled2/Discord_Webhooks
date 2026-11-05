import json
import os
import re
import time
import urllib.request

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL_4"]
APP_ID = 2073850          # THE FINALS on Steam
LOOKBACK_HOURS = 25       # post anything newer than this (matches a daily run)
KEYWORDS = []             # e.g. ["update", "patch", "season"] to only post matching titles
MAX_CHARS = 1500          # how much of each announcement to show

API = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
       f"?appid={APP_ID}&count=10&maxlength=0&format=json")
HEADERS = {"User-Agent": "Mozilla/5.0 (FinalsUpdatesBot/1.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
CLAN_IMG = "https://clan.fastly.steamstatic.com/images/"


def fetch_news():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["appnews"]["newsitems"]


def first_image(text):
    text = text.replace("{STEAM_CLAN_IMAGE}/", CLAN_IMG).replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    m = re.search(r"\[img\](https?://[^\[\s]+)\[/img\]", text, re.I)
    return m.group(1) if m else None


def clean(text):
    """Turn Steam's BBCode into Discord-friendly markdown."""
    text = re.sub(r"\[img\].*?\[/img\]", "", text, flags=re.I | re.S)
    text = re.sub(r"\[url=[^\]]*\](.*?)\[/url\]", r"\1", text, flags=re.I | re.S)
    text = re.sub(r"\[h[1-3]\](.*?)\[/h[1-3]\]", r"\n**\1**\n", text, flags=re.I | re.S)
    text = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", text, flags=re.I | re.S)
    text = re.sub(r"\[\*\]", "\n• ", text)
    text = re.sub(r"\[/?(list|olist|u|i|p|strike|quote|hr|previewyoutube|code|table|tr|td|th)[^\]]*\]", "", text, flags=re.I)
    text = re.sub(r"\[[^\]]{1,40}\]", "", text)          # any leftover tags
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit("\n", 1)[0].rstrip() + "\n…"
    return text


def main():
    cutoff = time.time() - LOOKBACK_HOURS * 3600
    items = [i for i in fetch_news() if i["date"] >= cutoff]
    if KEYWORDS:
        items = [i for i in items if any(k in i["title"].lower() for k in KEYWORDS)]
    if not items:
        print("No new announcements.")
        return

    embeds = []
    for item in sorted(items, key=lambda i: i["date"]):
        embed = {
            "title": item["title"][:250],
            "url": item["url"],
            "description": clean(item["contents"]) + "\n\n[Read the full post](" + item["url"] + ")",
            "color": 0xF5A623,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"])),
            "footer": {"text": "THE FINALS • via Steam"},
        }
        img = first_image(item["contents"])
        if img:
            embed["image"] = {"url": img}
        embeds.append(embed)

    for i in range(0, len(embeds), 3):   # keep each message small
        body = json.dumps({
            "username": "THE FINALS Updates",
            "content": "# 🎮 THE FINALS news" if i == 0 else "",
            "embeds": embeds[i:i + 3],
        }).encode()
        req = urllib.request.Request(WEBHOOK, data=body, headers=JSON_HEADERS)
        urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} announcement(s).")


if __name__ == "__main__":
    main()
