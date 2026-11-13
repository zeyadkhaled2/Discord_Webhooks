import html
import json
import os
import re
import time
import urllib.error
import urllib.request

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL_4"]
APP_ID = 2073850                  # THE FINALS on Steam
KEYWORDS = []                     # e.g. ["update", "patch", "season"] to only post matching titles
CHUNK = 3400                      # comfortable embed size so cards feel airy and readable
STATE_FILE = "finals_state.json"  # remembers which announcements were already posted

API = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
       f"?appid={APP_ID}&count=20&maxlength=0&format=json")
HEADERS = {"User-Agent": "Mozilla/5.0 (FinalsUpdatesBot/2.0)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
CLAN_IMG = "https://clan.fastly.steamstatic.com/images/"
STEAM_HUB_URL = f"https://store.steampowered.com/news/app/{APP_ID}"
FINALS_ICON = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/2073850/capsule_231x87.jpg"
FLAGS = re.I | re.S


# ---------- Steam ----------
def fetch_news():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r)["appnews"]["newsitems"]
    # only the developer's own announcements, not third-party news sites
    return [i for i in items if i.get("feedname") == "steam_community_announcements"]


# ---------- text conversion ----------
def extract_images(text):
    text = text.replace("{STEAM_CLAN_IMAGE}/", CLAN_IMG).replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    imgs = []
    for m in re.finditer(r"\[img\](https?://[^\[\s]+)\[/img\]", text, re.I):
        url = m.group(1).strip()
        if url not in imgs:
            imgs.append(url)
    return imgs


def classify_update(title):
    t = title.lower()
    if "hotfix" in t:
        return "🔧", "HOTFIX DEPLOYED", 0xFF6B35
    if "patch" in t or "update" in t or re.search(r"\b\d+\.\d+\.\d+\b", t):
        return "⚡", "ARENA PATCH NOTES", 0xD31E2B
    if "season" in t:
        return "🏆", "NEW SEASON DROP", 0xF5A623
    if "mid-season" in t or "event" in t:
        return "🎉", "SPECIAL ARENA EVENT", 0xE91E63
    return "📢", "OFFICIAL BROADCAST", 0xD31E2B


def convert_lists(text):
    out, depth, pos = [], 0, 0
    for m in re.finditer(r"\[(/?)(?:o?list)[^\]]*\]|\[\*\]|\[/\*\]", text, re.I):
        out.append(text[pos:m.start()])
        pos = m.end()
        tag = m.group(0).lower()
        if tag == "[/*]":
            continue
        if tag == "[*]":
            bullet = "• " if depth <= 1 else "◦ "
            out.append("\n" + "  " * max(depth - 1, 0) + bullet)
        elif m.group(1):
            depth = max(depth - 1, 0)
            out.append("\n")
        else:
            depth += 1
            out.append("\n")
    out.append(text[pos:])
    return "".join(out)


def to_markdown(text):
    text = html.unescape(text or "").replace("\r", "")
    text = re.sub(r"\[img\].*?\[/img\]", "", text, flags=FLAGS)
    text = re.sub(
        r"\[previewyoutube=([\w-]+)[^\]]*\]\s*\[/previewyoutube\]",
        r"\n🎬 **[Watch Official Video on YouTube ↗](https://youtu.be/\1)**\n",
        text,
        flags=re.I,
    )
    # headings with clean visual markers
    text = re.sub(
        r"\[h1\](.*?)\[/h1\]",
        lambda m: f"\n## 🔴 {m.group(1).strip()}\n",
        text,
        flags=FLAGS,
    )
    text = re.sub(
        r"\[h2\](.*?)\[/h2\]",
        lambda m: f"\n### 🔸 {m.group(1).strip()}\n",
        text,
        flags=FLAGS,
    )
    text = re.sub(
        r"\[h3\](.*?)\[/h3\]",
        lambda m: f"\n**▸ {m.group(1).strip()}**\n",
        text,
        flags=FLAGS,
    )
    # inline formatting
    text = re.sub(r"\[b\](.*?)\[/b\]", r"**\1**", text, flags=FLAGS)
    text = re.sub(r"\[i\](.*?)\[/i\]", r"*\1*", text, flags=FLAGS)
    text = re.sub(r"\[u\](.*?)\[/u\]", r"__\1__", text, flags=FLAGS)
    text = re.sub(r"\[strike\](.*?)\[/strike\]", r"~~\1~~", text, flags=FLAGS)
    text = re.sub(r"\[spoiler\](.*?)\[/spoiler\]", r"||\1||", text, flags=FLAGS)
    text = re.sub(r"\[url=([^\]]+)\](.*?)\[/url\]", r"[\2](\1)", text, flags=FLAGS)
    text = re.sub(r"\[url\](.*?)\[/url\]", r"\1", text, flags=FLAGS)
    text = re.sub(
        r"\[quote[^\]]*\](.*?)\[/quote\]",
        lambda m: "\n> 💬 *" + m.group(1).strip().replace("\n", "*\n> *") + "*\n",
        text,
        flags=FLAGS,
    )
    text = re.sub(r"\[code\](.*?)\[/code\]", r"```\n\1\n```", text, flags=FLAGS)
    text = re.sub(r"\[hr\]\s*\[/hr\]|\[hr\]", "\n-# ──────────────────────────────\n", text, flags=re.I)
    # tables -> simple rows separated by |
    text = re.sub(r"\[/t[dh]\]\s*", " | ", text, flags=re.I)
    text = re.sub(r"\[/tr\]", "\n", text, flags=re.I)
    text = re.sub(r" \| *\n", "\n", text)
    # Steam tags are lowercase, so this is case-sensitive and won't eat text like "[PC]"
    text = re.sub(r"\[/?(?:table|tr|td|th|p|noparse|center|left|right|expand|callout)(?:=[^\]]*)?\]", "", text)
    text = convert_lists(text)
    text = re.sub(r"\n(?:[ \t]*\n)+(?=[ \t]*[•◦] )", "\n", text)   # no blank lines between bullets
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text, limit=CHUNK):
    """Split text cleanly along section headings first, then line boundaries."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        is_major_heading = line.startswith("## 🔴 ") or line.startswith("### 🔸 ")
        # Start a fresh card on a major section heading if the current card is already substantial
        if is_major_heading and len(cur) >= 1400:
            chunks.append(cur)
            cur = ""
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
    raw_contents = item.get("contents") or ""
    text = to_markdown(raw_contents) or "*(No text in this announcement — click the title to view on Steam.)*"
    chunks = split_text(text)
    total = len(chunks)
    images = extract_images(raw_contents)
    unix_ts = int(item.get("date", time.time()))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix_ts))
    emoji, badge, accent_color = classify_update(item.get("title", ""))

    for n, chunk in enumerate(chunks, 1):
        footer = "Embark Studios • THE FINALS"
        if total > 1:
            footer += f"  •  Card {n} of {total}"

        embed = {
            "description": chunk,
            "color": accent_color if n == 1 else 0x2B2D31,
            "footer": {"text": footer},
        }
        payload = {
            "username": "THE FINALS • Arena Feed",
            "embeds": [embed],
        }

        if n == 1:
            embed["author"] = {
                "name": f"{emoji} {badge}  •  STEAM ANNOUNCEMENT",
                "url": STEAM_HUB_URL,
            }
            embed["title"] = f"🎮  {item['title'][:240]}"
            embed["url"] = item["url"]
            embed["timestamp"] = stamp
            if images:
                embed["image"] = {"url": images[0]}
            payload["content"] = (
                f"## {emoji} **{item['title']}**\n"
                f"-# 🕒 Dropped <t:{unix_ts}:R> (<t:{unix_ts}:f>)  •  "
                f"🔗 [**Read on Steam ↗**]({item['url']})"
            )
        else:
            # Attach secondary section banners if the Steam post included multiple images
            if n <= len(images):
                embed["image"] = {"url": images[n - 1]}

        if n == total:
            embed["fields"] = [
                {
                    "name": "🔗 Quick Links",
                    "value": (
                        f"[**📖 Full Patch Notes**]({item['url']})  •  "
                        f"[**📰 News Hub**]({STEAM_HUB_URL})  •  "
                        f"[**💬 Community Hub**](https://steamcommunity.com/app/{APP_ID}/discussions/)"
                    ),
                    "inline": False,
                }
            ]

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
        is_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        force_flag = os.environ.get("FORCE_POST", "true").lower() != "false"
        if is_manual and force_flag:
            latest = max(items or all_items, key=lambda i: i["date"])
            post_item(latest)
            print(f"Manual workflow_dispatch: force-posted latest announcement '{latest['title']}'.")
            return
        print("No new announcements.")
        return
    for item in new:
        post_item(item)
        posted.append(item["gid"])
        save_state(posted)           # saved after each success so nothing double-posts
        print(f"Posted: {item['title']}")


if __name__ == "__main__":
    main()
