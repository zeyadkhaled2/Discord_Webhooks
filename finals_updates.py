import json
import os
import re
import time
import urllib.error
import urllib.request

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL_4"]
APP_ID = 2073850                  # THE FINALS on Steam
KEYWORDS = []                     # e.g. ["update", "patch", "season"] to only post matching titles
CHUNK = 3900                      # max characters per Discord embed (limit is 4096)
STATE_FILE = "finals_state.json"  # remembers which announcements were already posted

API = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
       f"?appid={APP_ID}&count=20&maxlength=0&format=json")
HEADERS = {"User-Agent": "Mozilla/5.0 (FinalsUpdatesBot/1.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
CLAN_IMG = "https://clan.fastly.steamstatic.com/images/"
FLAGS = re.I | re.S


# ---------- Steam ----------
def fetch_news():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r)["appnews"]["newsitems"]
    # only the developer's own announcements, not third-party news sites
    return [i for i in items if i.get("feedname") == "steam_community_announcements"]


# ---------- text conversion ----------
def first_image(text):
    text = text.replace("{STEAM_CLAN_IMAGE}/", CLAN_IMG).replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    m = re.search(r"\[img\](https?://[^\[\s]+)\[/img\]", text, re.I)
    return m.group(1) if m else None


def convert_lists(text):
    out, depth, pos = [], 0, 0
    for m in re.finditer(r"\[(/?)(?:o?list)[^\]]*\]|\[\*\]|\[/\*\]", text, re.I):
        out.append(text[pos:m.start()])
        pos = m.end()
        tag = m.group(0).lower()
        if tag == "[/*]":
            continue
        if tag == "[*]":
            out.append("\n" + "  " * max(depth - 1, 0) + "- ")
        elif m.group(1):
            depth = max(depth - 1, 0)
            out.append("\n")
        else:
            depth += 1
            out.append("\n")
    out.append(text[pos:])
    return "".join(out)


def to_markdown(text):
    text = text.replace("\r", "")
    text = re.sub(r"\[img\].*?\[/img\]", "", text, flags=FLAGS)
    text = re.sub(r"\[previewyoutube=([\w-]+)[^\]]*\]\s*\[/previewyoutube\]",
                  r"▶ https://youtu.be/\1", text, flags=re.I)
    # headings
    text = re.sub(r"\[h1\](.*?)\[/h1\]", lambda m: f"\n## {m.group(1).strip()}\n", text, flags=FLAGS)
    text = re.sub(r"\[h2\](.*?)\[/h2\]", lambda m: f"\n### {m.group(1).strip()}\n", text, flags=FLAGS)
    text = re.sub(r"\[h3\](.*?)\[/h3\]", lambda m: f"\n**{m.group(1).strip()}**\n", text, flags=FLAGS)
    # inline formatting
    text = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", text, flags=FLAGS)
    text = re.sub(r"\[i\](.*?)\[/i\]", r"*\1*", text, flags=FLAGS)
    text = re.sub(r"\[u\](.*?)\[/u\]", r"__\1__", text, flags=FLAGS)
    text = re.sub(r"\[strike\](.*?)\[/strike\]", r"~~\1~~", text, flags=FLAGS)
    text = re.sub(r"\[spoiler\](.*?)\[/spoiler\]", r"||\1||", text, flags=FLAGS)
    text = re.sub(r"\[url=([^\]]+)\](.*?)\[/url\]", r"[\2](\1)", text, flags=FLAGS)
    text = re.sub(r"\[url\](.*?)\[/url\]", r"\1", text, flags=FLAGS)
    text = re.sub(r"\[quote[^\]]*\](.*?)\[/quote\]",
                  lambda m: "\n> " + m.group(1).strip().replace("\n", "\n> ") + "\n", text, flags=FLAGS)
    text = re.sub(r"\[code\](.*?)\[/code\]", r"```\n\1\n```", text, flags=FLAGS)
    text = re.sub(r"\[hr\]\s*\[/hr\]|\[hr\]", "\n──────────\n", text, flags=re.I)
    # tables -> simple rows separated by |
    text = re.sub(r"\[/t[dh]\]\s*", " | ", text, flags=re.I)
    text = re.sub(r"\[/tr\]", "\n", text, flags=re.I)
    text = re.sub(r" \| *\n", "\n", text)
    # Steam tags are lowercase, so this is case-sensitive and won't eat text like "[PC]"
    text = re.sub(r"\[/?(?:table|tr|td|th|p|noparse|center|left|right)(?:=[^\]]*)?\]", "", text)
    text = convert_lists(text)
    text = re.sub(r"\n(?:[ \t]*\n)+(?=[ \t]*- )", "\n", text)   # no blank lines between bullets
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text, limit=CHUNK):
    chunks, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + len(line) + 1 > limit:
            chunks.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]


# ---------- Discord ----------
def send(payload):
    data = json.dumps(payload).encode()
    for _ in range(6):
        req = urllib.request.Request(WEBHOOK, data=data, headers=JSON_HEADERS)
        try:
            urllib.request.urlopen(req, timeout=30)
            time.sleep(1.2)          # stay under Discord's webhook rate limit
            return
        except urllib.error.HTTPError as e:
            if e.code == 429:
                try:
                    wait = float(json.load(e).get("retry_after", 2))
                except Exception:
                    wait = 2.0
                time.sleep(wait + 0.5)
                continue
            raise
    raise RuntimeError("Discord rate limit did not clear")


def post_item(item):
    text = to_markdown(item["contents"]) or "(No text in this announcement.)"
    chunks = split_text(text)
    total = len(chunks)
    img = first_image(item["contents"])
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"]))
    for n, chunk in enumerate(chunks, 1):
        footer = "THE FINALS • via Steam"
        if total > 1:
            footer += f" • Part {n}/{total}"
        embed = {"description": chunk, "color": 0xF5A623, "footer": {"text": footer}}
        payload = {"username": "THE FINALS Updates", "embeds": [embed]}
        if n == 1:
            embed["title"] = item["title"][:250]
            embed["url"] = item["url"]
            embed["timestamp"] = stamp
            if img:
                embed["image"] = {"url": img}
            payload["content"] = "# 🎮 THE FINALS — new update"
        send(payload)


# ---------- state ----------
def load_state():
    try:
        with open(STATE_FILE) as f:
            return True, list(json.load(f)["posted"])
    except Exception:
        return False, []


def save_state(posted):
    with open(STATE_FILE, "w") as f:
        json.dump({"posted": posted[-100:]}, f, indent=2)


def main():
    all_items = fetch_news()
    if not all_items:
        print("Nothing returned from Steam.")
        return
    items = [i for i in all_items
             if not KEYWORDS or any(k in i["title"].lower() for k in KEYWORDS)]

    has_state, posted = load_state()
    if not has_state:
        # First run: post only the newest one as a test, and remember everything else
        latest = max(items or all_items, key=lambda i: i["date"])
        post_item(latest)
        save_state([i["gid"] for i in all_items])
        print("First run: posted the latest announcement and saved state.")
        return

    new = sorted((i for i in items if i["gid"] not in posted), key=lambda i: i["date"])
    if not new:
        print("No new announcements.")
        return
    for item in new:
        post_item(item)
        posted.append(item["gid"])
        save_state(posted)           # saved after each success so nothing double-posts
        print(f"Posted: {item['title']}")


if __name__ == "__main__":
    main()
