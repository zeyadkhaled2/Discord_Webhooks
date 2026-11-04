import json
import os
import urllib.request

WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
API = ("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
       "?locale=en-US&country=US&allowCountries=US")
HEADERS = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}


def fetch_games():
    req = urllib.request.Request(API, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return data["data"]["Catalog"]["searchStore"]["elements"]


def free_now(game):
    promos = game.get("promotions") or {}
    for group in promos.get("promotionalOffers") or []:
        for offer in group.get("promotionalOffers", []):
            if offer["discountSetting"]["discountPercentage"] == 0:
                return offer
    return None


def game_url(game):
    slug = game.get("productSlug") or game.get("urlSlug")
    mappings = game.get("offerMappings") or []
    if mappings:
        slug = mappings[0].get("pageSlug") or slug
    if not slug:
        return "https://store.epicgames.com/en-US/free-games"
    return f"https://store.epicgames.com/en-US/p/{slug.replace('/home', '')}"


def build_embeds(games):
    embeds = []
    for g in games:
        offer = free_now(g)
        if not offer:
            continue
        image = next((i["url"] for i in g.get("keyImages", [])
                      if i["type"] in ("OfferImageWide", "Thumbnail")), None)
        embed = {
            "title": g["title"],
            "url": game_url(g),
            "description": (g.get("description") or "")[:200],
            "color": 0x2F2F2F,
            "footer": {"text": "Free until " + offer["endDate"][:10]},
        }
        if image:
            embed["image"] = {"url": image}
        embeds.append(embed)
    return embeds


def main():
    embeds = build_embeds(fetch_games())
    if not embeds:
        print("No free games found.")
        return
    body = json.dumps({
        "username": "Epic Free Games",
        "content": "🎮 **Well, well, well. Look what decided to show up.!**",
        "embeds": embeds[:10],
    }).encode()
    req = urllib.request.Request(WEBHOOK, data=body, headers=HEADERS)
    urllib.request.urlopen(req, timeout=30)
    print(f"Posted {len(embeds)} game(s).")


if __name__ == "__main__":
    main()
