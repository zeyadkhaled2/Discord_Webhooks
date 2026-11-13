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
STATE_FILE = "finals_state.json"  # remembers which announcements were already posted

API = ("https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
       f"?appid={APP_ID}&count=20&maxlength=0&format=json")
HEADERS = {"User-Agent": "Mozilla/5.0 (FinalsUpdatesBot/3.2)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
CLAN_IMG = "https://clan.fastly.steamstatic.com/images/"
STEAM_HUB_URL = f"https://store.steampowered.com/news/app/{APP_ID}"
FLAGS = re.I | re.S

HIGHLIGHT_KEYWORDS = (
    "highlight", "overview", "welcome", "new mode", "game mode", "world tour",
    "event", "new feature", "season", "mid-season", "arena", "tournament",
    "community", "spotlight",
)
STORE_KEYWORDS = (
    "store", "shop", "cosmetic", "bundle", "outfit", "skin", "drip",
    "multibucks", "twitch drop", "battle pass", "sponsor",
)
WEAPON_KEYWORDS = (
    "weapon", "assault rifle", "smg", "lmg", "shotgun", "marksman", "sniper",
    "pistol", "handgun", "melee", "akm", "fcar", "xp-54", "m11", "v9s",
    "lh1", "model 1887", "sa1216", "lewis gun", "m60", "famas", "ks-23",
    "93r", "revolver", "r .357", "sh1900", "sr-84", "throwing knives",
    "sledgehammer", "riot shield", "dual blades", "spear", "recurved bow",
    "pike-556", "deagles", ".50 akimbo", "matter", "cerberus", "shak-50",
    "cb-01", "repeater", "arn-220", "minigun",
)
GADGET_KEYWORDS = (
    "gadget", "specialization", "archetype", "ability", "abilities",
    "cloaking", "evasive dash", "grappling hook", "healing beam",
    "dematerializer", "guardian turret", "charge 'n' slam", "mesh shield",
    "goo gun", "winch claw", "defibrillator", "jump pad", "zipline",
    "rpg-7", "c4", "dome shield", "barricade", "mine", "grenade",
    "aps turret", "sonar", "stun gun", "glitch", "gateway", "thermal bore",
    "data reshaper", "anti-gravity", "lockbolt", "nullifier",
)
BUGFIX_HEADER_KEYWORDS = (
    "content and bug fix", "bug fix", "bugfix", "known issue",
)
MINOR_KEYWORDS = (
    "bug fix", "bugfix", "fixes", "fixed", "audio", "ui", "user interface",
    "animation", "character", "controller", "performance", "stability",
    "crash", "security", "anti-cheat", "known issue", "localization",
    "spectator", "private match", "practice range", "tutorial", "settings",
    "voip", "voice chat", "contract", "progression", "ranked", "leaderboard",
    "map", "maps", "general", "quality of life", "qol", "visual", "vfx", "sfx",
)


# ---------- Steam ----------
def fetch_news():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r)["appnews"]["newsitems"]
    return [i for i in items if i.get("feedname") == "steam_community_announcements"]


def extract_images(text):
    text = text.replace("{STEAM_CLAN_IMAGE}/", CLAN_IMG).replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    imgs = []
    for m in re.finditer(r"\[img\](https?://[^\[\s]+)\[/img\]", text, re.I):
        url = m.group(1).strip()
        if url not in imgs:
            imgs.append(url)
    return imgs


def extract_youtube(text):
    m = re.search(r"\[previewyoutube=([\w-]+)[^\]]*\]", text or "", re.I)
    return f"https://youtu.be/{m.group(1)}" if m else None


def classify_update(title):
    t = title.lower()
    if "hotfix" in t:
        return "🔧", "HOTFIX DEPLOYED", 0xFF6B35
    if "season" in t and "mid" not in t:
        return "🏆", "NEW SEASON DROP", 0xFFB800
    if "mid-season" in t or "event" in t:
        return "🎉", "SPECIAL ARENA EVENT", 0xFF1E56
    return "⚡", "ARENA PATCH NOTES", 0xFF1E56


# ---------- BBCode cleanup & Colorful Formatting ----------
def colorize_bullet(line_text):
    """Add vibrant status emojis and highlight numbers inside balance bullets."""
    low = line_text.lower()
    line_text = re.sub(
        r"\bfrom\s+(\d+(?:\.\d+)?%?s?)\s+to\s+(\d+(?:\.\d+)?%?s?)\b",
        r"from `\1` ➔ **`\2`**",
        line_text,
        flags=re.I,
    )
    if any(w in low for w in ("increased damage", "reduced recoil", "reduced cooldown", "reduced reload", "buff", "improved", "added", "faster")):
        return f"🟢 `{line_text[:10].strip() if False else 'BUFF'}` {line_text}"
    if any(w in low for w in ("decreased damage", "increased recoil", "increased cooldown", "increased reload", "nerf", "removed", "slower")):
        return f"🔴 `NERF` {line_text}"
    if any(w in low for w in ("increased", "decreased", "reduced", "adjusted", "changed", "updated", "reworked")):
        return f"🟡 `TWEAK` {line_text}"
    if any(w in low for w in ("fixed", "resolved", "corrected")):
        return f"🛠️ {line_text}"
    return f"✨ {line_text}"


def convert_lists(text):
    out, depth, pos = [], 0, 0
    for m in re.finditer(r"\[(/?)(?:o?list)[^\]]*\]|\[\*\]|\[/\*\]", text, re.I):
        out.append(text[pos:m.start()])
        pos = m.end()
        tag = m.group(0).lower()
        if tag == "[/*]":
            continue
        if tag == "[*]":
            prefix = "__BULLET_TOP__" if depth <= 1 else "  ◦ "
            out.append("\n" + prefix)
        elif m.group(1):
            depth = max(depth - 1, 0)
            out.append("\n")
        else:
            depth += 1
            out.append("\n")
    out.append(text[pos:])
    joined = "".join(out)

    lines = []
    for line in joined.split("\n"):
        if line.startswith("__BULLET_TOP__"):
            content = line[len("__BULLET_TOP__"):].strip()
            lines.append(colorize_bullet(content) if content else "")
        else:
            lines.append(line)
    return "\n".join(lines)


def clean_bbcode_fragment(text):
    text = html.unescape(text or "").replace("\r", "")
    text = re.sub(r"\[img\].*?\[/img\]", "", text, flags=FLAGS)
    text = re.sub(r"\[previewyoutube=([\w-]+)[^\]]*\]\s*\[/previewyoutube\]", "", text, flags=re.I)
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
    text = re.sub(r"\[hr\]\s*\[/hr\]|\[hr\]", "", text, flags=re.I)
    text = re.sub(r"\[/t[dh]\]\s*", " | ", text, flags=re.I)
    text = re.sub(r"\[/tr\]", "\n", text, flags=re.I)
    text = re.sub(r" \| *\n", "\n", text)
    text = re.sub(r"\[/?(?:table|tr|td|th|p|noparse|center|left|right|expand|callout)(?:=[^\]]*)?\]", "", text)
    text = convert_lists(text)
    text = re.sub(r"\n(?:[ \t]*\n)+(?=[ \t]*(?:🟢|🔴|🟡|🛠️|✨|◦))", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_sections(raw_text):
    """Split BBCode into (heading_level, heading_title, cleaned_body) sections."""
    text = html.unescape(raw_text or "").replace("\r", "")
    # Normalize standalone bold lines that look like section/item headers into [h3]...[/h3]
    text = re.sub(
        r"(?:^|\n)[ \t]*\[b\]([^\[\n]{2,55})\[/b\][ \t]*(?=\n)",
        r"\n[h3]\1[/h3]\n",
        text,
        flags=re.I,
    )
    pattern = re.compile(r"\[h([1-5])\](.*?)\[/h\1\]", FLAGS)
    sections = []
    last_pos = 0
    current_level = 1
    current_title = "Highlights & Overview"

    for m in pattern.finditer(text):
        body = clean_bbcode_fragment(text[last_pos:m.start()])
        if body:
            sections.append((current_level, current_title, body))
        current_level = int(m.group(1))
        current_title = re.sub(r"\[/?[^\]]+\]", "", m.group(2)).strip().rstrip(":")
        last_pos = m.end()

    tail = clean_bbcode_fragment(text[last_pos:])
    if tail:
        sections.append((current_level, current_title, tail))
    return sections


def categorize_sections(sections):
    """Group sections into highlights, store, weapons, gadgets, and minor (Read More)."""
    buckets = {
        "highlights": [],
        "store": [],
        "weapons": [],
        "gadgets": [],
        "minor": [],
    }
    in_bugfix_zone = False
    active_cat = "highlights"

    for level, sec_title, body in sections:
        t = sec_title.lower().strip()

        # Check if a major heading enters or leaves the Bug Fixes zone
        if level in (1, 2):
            if any(k in t for k in BUGFIX_HEADER_KEYWORDS):
                in_bugfix_zone = True
                active_cat = "minor"
                buckets["minor"].append((level, sec_title, body))
                continue
            elif any(k in t for k in ("balance", "store", "shop", "highlight", "overview", "weapon", "gadget")):
                in_bugfix_zone = False

        if in_bugfix_zone:
            buckets["minor"].append((level, sec_title, body))
            continue

        if t == "highlights & overview":
            active_cat = "highlights"
        elif any(k in t for k in STORE_KEYWORDS):
            active_cat = "store"
        elif any(k in t for k in WEAPON_KEYWORDS):
            active_cat = "weapons"
        elif any(k in t for k in GADGET_KEYWORDS):
            active_cat = "gadgets"
        elif any(k in t for k in MINOR_KEYWORDS):
            active_cat = "minor"
        elif any(k in t for k in HIGHLIGHT_KEYWORDS):
            active_cat = "highlights"

        buckets[active_cat].append((level, sec_title, body))

    return buckets


def trim_block(text, max_chars, steam_url):
    """Keep a block within max_chars and append a clickable Read More link if trimmed."""
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    last_nl = cut.rfind("\n")
    if last_nl > max_chars // 2:
        cut = cut[:last_nl]
    cut = cut.rstrip()
    cut += f"\n\n✨ **[+ More in this section — Read More on Steam ↗]({steam_url})**"
    return cut, True


# ---------- Discord ----------
def send(payload):
    data = json.dumps(payload).encode()
    for _ in range(6):
        req = urllib.request.Request(WEBHOOK, data=data, headers=JSON_HEADERS)
        try:
            urllib.request.urlopen(req, timeout=30)
            time.sleep(1.2)
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
    steam_url = item["url"]
    images = extract_images(raw_contents)
    yt_url = extract_youtube(raw_contents)
    unix_ts = int(item.get("date", time.time()))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix_ts))
    emoji, badge, main_color = classify_update(item.get("title", ""))

    sections = parse_sections(raw_contents)
    buckets = categorize_sections(sections)

    embeds = []

    # ==================== CARD 1: HUGE HIGHLIGHTS & STORE UPDATES ====================
    card1_parts = [
        "```ansi\n"
        "\u001b[1;31m🔥 THE FINALS\u001b[0m \u001b[1;33m• MAJOR HIGHLIGHTS & STORE DROPS\u001b[0m\n"
        "```"
    ]
    if yt_url:
        card1_parts.append(f"## 🎬 [Watch Official Update Trailer on YouTube ↗]({yt_url})")

    for level, sec_title, body in buckets["highlights"]:
        if sec_title != "Highlights & Overview":
            card1_parts.append(f"# 🔥 [{sec_title.upper()}]({steam_url})\n{body}")
        else:
            card1_parts.append(f"# 🌟 [MAJOR UPDATE OVERVIEW]({steam_url})\n{body}")

    if buckets["store"]:
        store_lines = [f"# 🛍️ [STORE & COSMETIC DROPS]({steam_url})"]
        for level, sec_title, body in buckets["store"]:
            if sec_title.lower() not in ("store", "shop", "store update", "store updates", "cosmetics"):
                store_lines.append(f"## 💎 [{sec_title}]({steam_url})\n{body}")
            else:
                store_lines.append(body)
        card1_parts.append("\n\n".join(store_lines))

    card1_text, _ = trim_block("\n\n".join(card1_parts), 1850, steam_url)
    embed1 = {
        "author": {
            "name": f"{emoji} {badge}  •  EMBARK STUDIOS",
            "url": STEAM_HUB_URL,
        },
        "title": f"🎮  {item['title'][:240]}",
        "url": steam_url,
        "description": card1_text,
        "color": main_color,  # Vibrant Neon Crimson / Gold
        "timestamp": stamp,
        "footer": {"text": "🟥 Major Highlights & Store Updates • THE FINALS"},
    }
    if images:
        embed1["image"] = {"url": images[0]}
    embeds.append(embed1)

    # ==================== CARD 2: WEAPON & GADGET CHANGES ====================
    if buckets["weapons"] or buckets["gadgets"]:
        card2_parts = [
            "```ansi\n"
            "\u001b[1;36m⚡ COMBAT BALANCE\u001b[0m \u001b[1;32m• WEAPONS, GADGETS & SPECS\u001b[0m\n"
            "```"
        ]

        if buckets["weapons"]:
            w_lines = [f"# 🔫 [WEAPON CHANGES]({steam_url})"]
            for level, sec_title, body in buckets["weapons"]:
                if sec_title.lower() not in ("weapons", "weapon", "weapon changes", "balance"):
                    w_lines.append(f"## ⚡ [{sec_title}]({steam_url})\n{body}")
                else:
                    w_lines.append(body)
            w_block, _ = trim_block("\n\n".join(w_lines), 1000, steam_url)
            card2_parts.append(w_block)

        if buckets["gadgets"]:
            g_lines = [f"# 💣 [GADGETS & SPECIALIZATIONS]({steam_url})"]
            for level, sec_title, body in buckets["gadgets"]:
                if sec_title.lower() not in ("gadgets", "gadget", "specializations", "archetypes", "abilities"):
                    g_lines.append(f"## 🛡️ [{sec_title}]({steam_url})\n{body}")
                else:
                    g_lines.append(body)
            g_block, _ = trim_block("\n\n".join(g_lines), 1000, steam_url)
            card2_parts.append(g_block)

        card2_text, _ = trim_block("\n\n".join(card2_parts), 2100, steam_url)
        embed2 = {
            "description": card2_text,
            "color": 0x00E5FF,  # Vibrant Cyber Cyan
            "footer": {"text": "🟦 Weapon & Gadget Balance • THE FINALS"},
        }
        if len(images) > 1:
            embed2["image"] = {"url": images[1]}
        embeds.append(embed2)

    # ==================== COMPACT "READ MORE" CARD FOR EVERYTHING ELSE ====================
    minor_titles = []
    minor_preview_lines = []
    for _, sec_title, body in buckets["minor"]:
        if sec_title not in minor_titles:
            minor_titles.append(sec_title)
        first_lines = [ln.strip() for ln in body.split("\n") if ln.strip()][:2]
        if first_lines:
            minor_preview_lines.append(f"**{sec_title}:** " + " / ".join(first_lines)[:130])

    read_more_parts = [
        "```ansi\n"
        "\u001b[1;35m📖 READ MORE\u001b[0m \u001b[1;33m• BUG FIXES, MAPS, AUDIO & FULL NOTES\u001b[0m\n"
        "```"
    ]
    if minor_titles:
        pills = "  •  ".join(f"`🛠️ {t}`" for t in minor_titles[:8])
        read_more_parts.append(f"## 🧩 [Also Covered in This Update]({steam_url})\n{pills}")
        if minor_preview_lines:
            spoiler_body = "\n".join(minor_preview_lines[:5])[:600]
            read_more_parts.append(
                f"🔽 **Click the spoiler bar below for a quick peek:**\n||{spoiler_body}||"
            )

    read_more_parts.append(
        f"# 👉 [📖 READ FULL PATCH NOTES ON STEAM ↗]({steam_url})\n"
        f"-# [📰 All Steam News]({STEAM_HUB_URL})  •  "
        f"[💬 Steam Discussions](https://steamcommunity.com/app/{APP_ID}/discussions/)"
    )

    embeds.append({
        "description": "\n\n".join(read_more_parts),
        "color": 0x9D4EDD,  # Vibrant Royal Purple
        "footer": {"text": "🟪 Compact View • Click Read Full Patch Notes above for every detail"},
    })

    payload = {
        "username": "THE FINALS • Arena Feed",
        "content": (
            f"# {emoji} **{item['title']}**\n"
            f"-# 🕒 Live <t:{unix_ts}:R> (<t:{unix_ts}:f>)  •  "
            f"✨ [**Click Here for Full Steam Patch Notes ↗**]({steam_url})"
        ),
        "embeds": embeds,
    }
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
        save_state(posted)
        print(f"Posted: {item['title']}")


if __name__ == "__main__":
    main()
