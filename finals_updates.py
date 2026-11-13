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
HEADERS = {"User-Agent": "Mozilla/5.0 (FinalsUpdatesBot/4.1)"}
JSON_HEADERS = {**HEADERS, "Content-Type": "application/json"}
CLAN_IMG = "https://clan.fastly.steamstatic.com/images/"
STEAM_HUB_URL = f"https://store.steampowered.com/news/app/{APP_ID}"
FLAGS = re.I | re.S

STORE_HEADER_WORDS = (
    "store", "shop", "esport bundle", "bundle", "cosmetic", "event pass",
    "twitch drop", "battle pass", "set",
)
BUGFIX_SUBSECTIONS = {
    "animation", "animations", "audio", "characters", "character", "controller",
    "contracts", "cosmetic", "cosmetics", "maps", "map", "modes", "performance",
    "progression", "private match", "practice range", "ranked", "security",
    "settings", "social", "spectator", "stability", "tutorial", "ui",
    "user interface", "vfx", "sfx", "voip", "voice chat", "known issues",
}


# ---------- Steam ----------
def fetch_news():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        items = json.load(r)["appnews"]["newsitems"]
    return [i for i in items if i.get("feedname") == "steam_community_announcements"]


def extract_images(text):
    text = (text or "").replace("{STEAM_CLAN_IMAGE}/", CLAN_IMG).replace("{STEAM_CLAN_IMAGE}", CLAN_IMG)
    imgs = []
    for m in re.finditer(r'\[img(?:\s+[^\]]*src="?(https?://[^"\]\s]+)"?[^\]]*)?\](https?://[^\[\s]+)?\[/img\]', text, re.I):
        url = (m.group(1) or m.group(2) or "").strip()
        if url and url not in imgs:
            imgs.append(url)
    return imgs


def classify_update(title):
    t = title.lower()
    if "hotfix" in t:
        return "🔧", "HOTFIX DEPLOYED", 0xFF6B35
    if "season" in t and "mid" not in t:
        return "🏆", "NEW SEASON DROP", 0xFFB800
    if "mid-season" in t or "event" in t:
        return "🎉", "SPECIAL ARENA EVENT", 0xFF2A54
    return "⚡", "ARENA UPDATE", 0xFF2A54


# ---------- BBCode cleanup & Colorful Formatting ----------
def colorize_bullet(line_text):
    """Add compact color indicators and highlight numbers in balance changes."""
    low = line_text.lower()
    line_text = re.sub(
        r"\bfrom\s+([\d,.]+(?:\.\d+)?%?s?)\s+to\s+([\d,.]+(?:\.\d+)?%?s?)\b",
        r"from `\1` ➔ **`\2`**",
        line_text,
        flags=re.I,
    )
    if any(w in low for w in (
        "increased damage", "reduced recoil", "reduced cooldown", "reduced reload",
        "buff", "improved", "added", "faster", "increased ammo", "increased the heat",
        "increased contestant heat", "slightly increased", "can now earn",
    )):
        return f"🟢 {line_text}"
    if any(w in low for w in (
        "decreased damage", "decreased impact", "decreased health", "decreased max",
        "increased recoil", "increased cooldown", "increased deploy", "decreased glitch",
        "decreased shockwave", "decreased the heat", "nerf", "removed", "slower",
    )):
        return f"🔴 {line_text}"
    if any(w in low for w in ("increased", "decreased", "reduced", "adjusted", "changed", "updated", "re-aligned", "reworked")):
        return f"🟡 {line_text}"
    if any(w in low for w in ("fixed", "resolved", "corrected", "prevented")):
        return f"🛠️ {line_text}"
    return f"🔸 {line_text}"


def convert_lists(text):
    # Collapse [p] tags immediately inside [*] so bullet text stays on the same line
    text = re.sub(r"\[\*\]\s*\[p\]", "[*]", text, flags=re.I)
    text = re.sub(r"\[/p\]\s*\[/\*\]", "[/*]", text, flags=re.I)

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
    # Collapse any newline immediately after __BULLET_TOP__
    joined = re.sub(r"__BULLET_TOP__\s+", "__BULLET_TOP__", joined)

    lines = []
    for line in joined.split("\n"):
        s = line.strip()
        if s.startswith("__BULLET_TOP__"):
            content = s[len("__BULLET_TOP__"):].strip()
            lines.append(colorize_bullet(content) if content else "")
        else:
            lines.append(line)
    return "\n".join(lines)


def clean_bbcode(text, drop_dev_notes=True):
    text = html.unescape(text or "").replace("\r", "")
    # Remove [img]...[/img] and [img src="..."][/img]
    text = re.sub(r"\[img[^\]]*\].*?\[/img\]", "\n", text, flags=FLAGS)
    # Convert YouTube previews (with or without quotes)
    text = re.sub(
        r'\[previewyoutube="?([\w-]+)[^"\]]*"?[^\]]*\]\s*\[/previewyoutube\]',
        r"\n🎬 [Watch Video Clip ↗](https://youtu.be/\1)\n",
        text,
        flags=re.I,
    )

    # URLs (with or without quotes around href)
    text = re.sub(r'\[url="?([^"\]\s]+)"?\](.*?)\[/url\]', r"[\2](\1)", text, flags=FLAGS)
    text = re.sub(r"\[url\](.*?)\[/url\]", r"\1", text, flags=FLAGS)

    # Inline formatting
    text = re.sub(r"\[b\](.*?)\[/b\]", lambda m: f"**{m.group(1).strip()}**" if m.group(1).strip() else "", text, flags=FLAGS)
    text = re.sub(r"\[i\](.*?)\[/i\]", lambda m: f"*{m.group(1).strip()}*" if m.group(1).strip() else "", text, flags=FLAGS)
    text = re.sub(r"\[u\](.*?)\[/u\]", r"__\1__", text, flags=FLAGS)
    text = re.sub(r"\[strike\](.*?)\[/strike\]", r"~~\1~~", text, flags=FLAGS)
    text = re.sub(r"\[spoiler\](.*?)\[/spoiler\]", r"||\1||", text, flags=FLAGS)
    text = re.sub(
        r"\[quote[^\]]*\](.*?)\[/quote\]",
        lambda m: "\n> 💬 *" + m.group(1).strip().replace("\n", "*\n> *") + "*\n",
        text,
        flags=FLAGS,
    )
    text = re.sub(r"\[code\](.*?)\[/code\]", r"```\n\1\n```", text, flags=FLAGS)
    text = re.sub(r"\[hr\]\s*\[/hr\]|\[hr\]", "\n", text, flags=re.I)
    text = re.sub(r"\[/?(?:table|tr|td|th|noparse|center|left|right|expand|callout)(?:=[^\]]*)?\]", "", text)

    # Convert lists before stripping remaining [p] tags so [*]...[p]...[/p] stays attached
    text = convert_lists(text)

    # Paragraph breaks become newlines so [p][b]Header[/b][/p] stays on its own line
    text = re.sub(r"\[/p\]\s*\[p\]", "\n\n", text, flags=re.I)
    text = re.sub(r"\[/?p\]", "\n", text, flags=re.I)

    cleaned_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if drop_dev_notes and re.match(r"^\*?(?:\*\*?)?dev\s*notes?:?", stripped, re.I):
            continue
        cleaned_lines.append(stripped)

    result = "\n".join(cleaned_lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def split_top_blocks(raw_text):
    """Split announcement by [h1]/[h2]/[h3] headers."""
    text = html.unescape(raw_text or "").replace("\r", "")
    pattern = re.compile(r"\[h([1-4])\](.*?)\[/h\1\]", FLAGS)
    blocks = []
    last_pos = 0
    current_title = "INTO THE SPOTLIGHT"

    for m in pattern.finditer(text):
        body = text[last_pos:m.start()]
        if body.strip():
            blocks.append((current_title, body))
        raw_heading = m.group(2)
        raw_heading = re.sub(r"\[img[^\]]*\].*?\[/img\]", "", raw_heading, flags=FLAGS)
        current_title = re.sub(r"\[/?[^\]]+\]", "", raw_heading).strip()
        last_pos = m.end()

    tail = text[last_pos:]
    if tail.strip():
        blocks.append((current_title, tail))
    return blocks


def parse_balance_subsections(raw_block):
    """
    Parse a GAME UPDATE / BALANCE CHANGES block into (header, lines) pairs,
    preserving empty category headers like **Gadgets**, **Weapons**, **Specializations**
    so the state machine knows when a new category starts!
    """
    cleaned = clean_bbcode(raw_block, drop_dev_notes=True)
    groups = []
    current_header = None
    current_lines = []

    for line in cleaned.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = re.match(r"^\*\*([^*]{2,45})\*\*$", s)
        if m:
            if current_header is not None:
                groups.append((current_header, current_lines))
            current_header = m.group(1).strip()
            current_lines = []
        else:
            if current_header is None:
                current_header = "General"
            current_lines.append(s)

    if current_header is not None:
        groups.append((current_header, current_lines))
    return groups


def summarize_highlight_block(title, raw_body):
    """Create a concise, colorful summary of a highlight or store block."""
    cleaned = clean_bbcode(raw_body, drop_dev_notes=True)
    cleaned = re.sub(r"^\*\*INTO THE SPOTLIGHT\*\*\s*", "", cleaned, flags=re.I).strip()
    lines = [ln.strip() for ln in cleaned.split("\n") if ln.strip()]
    if not lines:
        return ""

    prose, bullets, video_line = [], [], None
    for ln in lines:
        if ln.startswith("🎬"):
            video_line = ln
        elif ln.startswith(("🟢", "🔴", "🟡", "🛠️", "🔸", "◦")):
            bullets.append(ln)
        else:
            prose.append(ln)

    summary_parts = []
    if prose:
        first_para = " ".join(prose[:2])
        if len(first_para) > 150:
            first_para = first_para[:147].rstrip() + "..."
        summary_parts.append(first_para)
    if bullets:
        summary_parts.append("\n".join(bullets[:3]))
    if video_line:
        summary_parts.append(video_line)

    body_str = "\n".join(summary_parts)
    return f"🔸 **`{title}`**\n{body_str}"


def build_update_embeds(item):
    raw_contents = item.get("contents") or ""
    steam_url = item["url"]
    images = extract_images(raw_contents)
    unix_ts = int(item.get("date", time.time()))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(unix_ts))
    emoji, badge, _ = classify_update(item.get("title", ""))

    blocks = split_top_blocks(raw_contents)

    major_sections = []
    store_sections = []
    weapon_items = []
    gadget_items = []
    other_balance_items = []
    bugfix_categories = []
    bugfix_samples = []

    for title, raw_body in blocks:
        t_low = title.lower()

        if any(k in t_low for k in ("balance", "game update", "bug fix", "patch notes", "changes")):
            subgroups = parse_balance_subsections(raw_body)
            non_empty = [(h, lns) for h, lns in subgroups if lns]
            first_headers = [h.lower() for h, _ in subgroups[:3]]
            all_bullets = [ln for _, lns in non_empty for ln in lns]
            fixed_count = sum(1 for ln in all_bullets if "🛠️" in ln or "fixed" in ln.lower())
            is_bugfix_block = (
                "bug fix" in t_low
                or (first_headers and first_headers[0] in BUGFIX_SUBSECTIONS)
                or (all_bullets and fixed_count / len(all_bullets) > 0.6)
            )

            if is_bugfix_block:
                for h, lns in subgroups:
                    if h not in bugfix_categories and h.lower() in BUGFIX_SUBSECTIONS | {"gadgets", "weapon", "weapons", "specialization", "specializations", "gameplay", "game modes"}:
                        bugfix_categories.append(h)
                    if lns and len(bugfix_samples) < 5:
                        bugfix_samples.append(f"**{h}:** {lns[0][:100]}")
                continue

            # Real Balance Changes block! Track category mode across empty category headers
            mode = "other_balance"
            for h, lns in subgroups:
                h_low = h.lower().strip()
                if h_low in ("weapons", "weapon"):
                    mode = "weapons"
                    if lns:
                        weapon_items.append(("General Weapons", lns))
                    continue
                if h_low in ("gadgets", "gadget"):
                    mode = "gadgets"
                    if lns:
                        gadget_items.append(("General Gadgets", lns))
                    continue
                if h_low in ("specializations", "specialization", "archetypes", "archetype"):
                    mode = "gadgets"
                    if lns:
                        gadget_items.append((f"{h} (Spec)", lns))
                    continue
                if h_low in ("game mode", "game modes", "gameplay", "arena carriables", "arena carribales"):
                    mode = "other_balance"
                    if lns:
                        other_balance_items.append((h, lns))
                    continue

                if not lns:
                    continue

                if h_low == "general":
                    label = "General Gadgets" if mode == "gadgets" else ("General Weapons" if mode == "weapons" else "General Arena")
                else:
                    label = h

                if mode == "weapons":
                    weapon_items.append((label, lns))
                elif mode == "gadgets":
                    gadget_items.append((label, lns))
                else:
                    other_balance_items.append((label, lns))
            continue

        if any(k in t_low for k in STORE_HEADER_WORDS):
            store_sections.append(summarize_highlight_block(title, raw_body))
        else:
            major_sections.append(summarize_highlight_block(title, raw_body))

    embeds = []

    # ==================== CARD 1: MAJOR UPDATES & STORE DROPS ====================
    card1_parts = [
        "```ansi\n"
        "\u001b[1;31m🔥 MAJOR UPDATES\u001b[0m \u001b[1;33m& STORE DROPS\u001b[0m\n"
        "```"
    ]
    if major_sections:
        card1_parts.append(
            f"### 🌟 [Major Updates & Events]({steam_url})\n"
            + "\n\n".join(s for s in major_sections if s)
        )
    if store_sections:
        card1_parts.append(
            f"### 🛍️ [Store Updates, Bundles & Drops]({steam_url})\n"
            + "\n\n".join(s for s in store_sections if s)
        )

    card1_desc = "\n\n".join(card1_parts)[:2500]
    embed1 = {
        "author": {
            "name": f"{emoji} {badge}  •  THE FINALS",
            "url": STEAM_HUB_URL,
        },
        "title": f"🎮  {item['title'][:240]}",
        "url": steam_url,
        "description": card1_desc,
        "color": 0xFF2A54,  # Vibrant Crimson Red
        "timestamp": stamp,
        "footer": {"text": "🟥 Card 1 of 2 • Major Highlights & Store Updates"},
    }
    if images:
        embed1["image"] = {"url": images[0]}
    embeds.append(embed1)

    # ==================== CARD 2: WEAPON & GADGET CHANGES + READ MORE ====================
    card2_parts = [
        "```ansi\n"
        "\u001b[1;36m⚔️ COMBAT BALANCE\u001b[0m \u001b[1;32m• WEAPONS & GADGETS\u001b[0m\n"
        "```\n"
        "-# `🟢 Buff`   `🔴 Nerf`   `🟡 Adjustment`"
    ]

    if weapon_items:
        w_blocks = [f"### 🔫 [Weapon Changes]({steam_url})"]
        for name, lns in weapon_items:
            w_blocks.append(f"**⚡ `{name}`**\n" + "\n".join(lns))
        card2_parts.append("\n\n".join(w_blocks))

    if gadget_items:
        g_blocks = [f"### 💣 [Gadget & Specialization Changes]({steam_url})"]
        for name, lns in gadget_items:
            g_blocks.append(f"**🛡️ `{name}`**\n" + "\n".join(lns))
        card2_parts.append("\n\n".join(g_blocks))

    if other_balance_items:
        o_blocks = [f"### 🎯 [Arena & Gameplay Tweaks]({steam_url})"]
        for name, lns in other_balance_items:
            o_blocks.append(f"**🔸 `{name}`**\n" + "\n".join(lns[:2]))
        card2_parts.append("\n\n".join(o_blocks))

    read_more_lines = [f"### 📖 [Other Changes & Bug Fixes (Read More)]({steam_url})"]
    if bugfix_categories:
        pills = " • ".join(f"`{c}`" for c in bugfix_categories[:10])
        read_more_lines.append(f"-# 🛠️ **Also fixed in:** {pills}")
    if bugfix_samples:
        spoiler_preview = "\n".join(bugfix_samples[:5])[:500]
        read_more_lines.append(f"🔽 *Click box to preview minor fixes:*\n||{spoiler_preview}||")
    read_more_lines.append(
        f"👉 **[📖 Click Here to Read All Bug Fixes & Dev Notes on Steam ↗]({steam_url})**"
    )
    card2_parts.append("\n".join(read_more_lines))

    card2_desc = "\n\n".join(card2_parts)[:3300]
    embed2 = {
        "description": card2_desc,
        "color": 0x00E5FF,  # Vibrant Cyber Cyan
        "footer": {"text": "🟦 Card 2 of 2 • Weapons, Gadgets & Read More"},
    }
    if len(images) > 1:
        embed2["image"] = {"url": images[1]}
    embeds.append(embed2)

    payload = {
        "username": "THE FINALS • Arena Feed",
        "content": (
            f"### {emoji} **THE FINALS — {item['title']}**\n"
            f"-# 🕒 Released <t:{unix_ts}:R> (<t:{unix_ts}:f>)  •  "
            f"🔗 [**Open Full Notes on Steam ↗**]({steam_url})"
        ),
        "embeds": embeds,
    }
    return payload


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
    payload = build_update_embeds(item)
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
