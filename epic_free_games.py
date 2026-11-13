import json
import os
import urllib.request
from datetime import datetime, timezone

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
API = ("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
       "?locale=en-US&country=US&allowCountries=US")
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
STORE_URL = "https://store.epicgames.com/en-US/free-games"

CARD_COLORS = [0x00E676, 0x00E5FF, 0xFFB800, 0xFF1E56]


def fetch_games():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["data"]["Catalog"]["searchStore"]["elements"]


def parse_iso_timestamp(iso_str):
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def free_now(game):
    promos = game.get("promotions") or {}
    for group in promos.get("promotionalOffers") or []:
        for offer in group.get("promotionalOffers", []):
            if offer.get("discountSetting", {}).get("discountPercentage") == 0:
                return offer
    return None


def upcoming_free(game):
    promos = game.get("promotions") or {}
    for group in promos.get("upcomingPromotionalOffers") or []:
        for offer in group.get("promotionalOffers", []):
            if offer.get("discountSetting", {}).get("discountPercentage") == 0:
                return offer
    return None


def game_url(game):
    slug = game.get("productSlug") or game.get("urlSlug")
    mappings = game.get("offerMappings") or []
    if mappings:
        slug = mappings[0].get("pageSlug") or slug
    if not slug or slug == "[]":
        return STORE_URL
    return f"https://store.epicgames.com/en-US/p/{slug.replace('/home', '')}"


def pick_image(game):
    preferred = ("OfferImageWide", "DieselStoreFrontWide", "VaultClosed", "Thumbnail")
    images = game.get("keyImages") or []
    for kind in preferred:
        for img in images:
            if img.get("type") == kind and img.get("url"):
                return img["url"]
    return images[0]["url"] if images and images[0].get("url") else None


def original_price_label(game):
    try:
        fmt = game["price"]["totalPrice"]["fmtPrice"]["originalPrice"]
        if fmt and fmt != "0":
            return f"~~{fmt}~~ ➔ **`FREE`**"
    except Exception:
        pass
    return "**`100% FREE`**"


def build_embeds(games):
    embeds = []
    upcoming_lines = []

    for g in games:
        offer = free_now(g)
        if offer:
            url = game_url(g)
            image = pick_image(g)
            desc = (g.get("description") or "Grab this title for free on the Epic Games Store and keep it forever!").strip()
            short_desc = desc if len(desc) <= 180 else desc[:177].rstrip() + "..."

            end_ts = parse_iso_timestamp(offer.get("endDate"))
            if end_ts:
                deadline = f"🟢 <t:{end_ts}:R>\n-# Ends <t:{end_ts}:d>"
            else:
                deadline = f"🟢 Until {(offer.get('endDate') or '')[:10]}"

            seller = (g.get("seller") or {}).get("name") or "Epic Games"
            color = CARD_COLORS[len(embeds) % len(CARD_COLORS)]

            embed = {
                "author": {
                    "name": "🎁 FREE RIGHT NOW  •  EPIC GAMES STORE",
                    "url": STORE_URL,
                },
                "title": f"🎮  {g['title']}",
                "url": url,
                "description": (
                    "```ansi\n"
                    "\u001b[1;32m✨ 100% FREE TO KEEP FOREVER\u001b[0m \u001b[1;36m• WEEKLY DROP\u001b[0m\n"
                    "```\n"
                    f"### 🔥 [{g['title']}]({url})\n"
                    f"> {short_desc}\n\n"
                    f"👉 **[🛒 Claim Free Game Now ↗]({url})**"
                ),
                "color": color,
                "fields": [
                    {"name": "💰 Store Value", "value": original_price_label(g), "inline": True},
                    {"name": "🏢 Studio", "value": f"`{seller}`", "inline": True},
                    {"name": "⏳ Claim Before", "value": deadline, "inline": True},
                ],
                "footer": {"text": "🟩 Epic Games Weekly Freebie • Click Claim above"},
            }
            if image:
                embed["image"] = {"url": image}
            embeds.append(embed)
            continue

        next_offer = upcoming_free(g)
        if next_offer:
            url = game_url(g)
            start_ts = parse_iso_timestamp(next_offer.get("startDate"))
            when = f"unlocks <t:{start_ts}:R>" if start_ts else f"unlocks {(next_offer.get('startDate') or '')[:10]}"
            upcoming_lines.append(f"🟣 **[**{g['title']}**]({url})** — *{when}*")

    if upcoming_lines and len(embeds) < 10:
        embeds.append({
            "description": (
                "```ansi\n"
                "\u001b[1;35m🔮 NEXT WEEK'S ROTATION\u001b[0m \u001b[1;33m• SNEAK PEEK\u001b[0m\n"
                "```\n"
                "### 🔮 Coming Next Week\n"
                + "\n".join(upcoming_lines[:5])
                + f"\n\n-# 👉 [Browse All Epic Freebies ↗]({STORE_URL})"
            ),
            "color": 0x9D4EDD,
            "footer": {"text": "🟪 Set a reminder • Next week's Epic Store rotation"},
        })

    return embeds


def main():
    embeds = build_embeds(fetch_games())
    if not embeds:
        print("No free games found.")
        return
    now_ts = int(datetime.now(timezone.utc).timestamp())
    body = json.dumps({
        "username": "Epic Store • Freebie Radar",
        "content": (
            "### 🎁 **This Week's Free Games Are Live!**\n"
            f"-# Grab them before the rotation resets • Checked <t:{now_ts}:R>"
        ),
        "embeds": embeds[:10],
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} embed(s).")


if __name__ == "__main__":
    main()
