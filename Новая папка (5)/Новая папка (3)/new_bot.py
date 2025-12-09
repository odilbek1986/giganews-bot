import asyncio
import html
import re
import feedparser
from aiogram import Bot

# ============================
#   CONFIG (TOKEN & CHANNEL)
# ============================

TOKEN = "8383119570:AAGu7FtVxrzcjy81w23MSI9HboVr7QaManA"  # <-- shu yerga token qo'ying
CHANNEL_ID = -1003369735509     # <-- shu yerga kanal ID qo'ying

SUMMARY_MAX_SENTENCES = 3
SUMMARY_MAX_CHARS = 180
MAX_POSTS_PER_FEED = 2

SEEN_FILE = "seen_ids.txt"
CHECK_INTERVAL = 600  # 10 daqiqa


# ============================
#        RSS MANBALAR
# ============================

RSS_FEEDS = [
    {
        "name": "BBC World",
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "world",
    },
    {
        "name": "Reuters World",
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "category": "world",
    },
    {
        "name": "Lenta.ru",
        "url": "https://lenta.ru/rss",
        "category": "russian",
    },
    {
        "name": "Kun.uz",
        "url": "https://kun.uz/news/rss",
        "category": "uzbek",
    },
]


# ============================
#        CATEGORY TAGS
# ============================

CATEGORIES = {
    "world": "#World",
    "russian": "#Russia",
    "uzbek": "#Uzbek",
    "economy": "#Economy",
    "other": "#News"
}


# ============================
#     HELPERS & CLEANERS
# ============================

def clean_html(text):
    text = re.sub(r"<.*?>", "", text or "")
    text = text.replace("&nbsp;", " ")
    return text.strip()


def split_sentences(text: str) -> list:
    """Matndan oddiy gaplarni ajratadi."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"[.!?]", text)
    sentences = [p.strip() for p in parts if p.strip()]
    return sentences


def summarize_to_bullets(summary: str) -> list:
    """3 ta bulletga qisqartiradi."""
    summary = clean_html(summary or "")
    sentences = split_sentences(summary)
    bullets = []

    for s in sentences[:SUMMARY_MAX_SENTENCES]:
        if len(s) > SUMMARY_MAX_CHARS:
            s = s[:SUMMARY_MAX_CHARS] + "..."
        bullets.append(s)

    return bullets


# ============================
#     POST BUILDER
# ============================

def build_message(entry, feed_def) -> str:
    category_key = feed_def.get("category", "other")
    category_tag = CATEGORIES.get(category_key, "#News")

    emoji_map = {
        "world": "🌍",
        "russian": "🇷🇺",
        "uzbek": "🇺🇿",
        "economy": "💰",
        "other": "🛰",
    }
    cat_emoji = emoji_map.get(category_key, "🛰")

    title = clean_html(getattr(entry, "title", "") or "")
    summary_raw = getattr(entry, "summary", "") or ""
    link = getattr(entry, "link", "") or getattr(entry, "id", "")

    bullets = summarize_to_bullets(summary_raw)
    
    # HTML encode
    title_html = html.escape(title)
    link_html = html.escape(link)
    src_html = html.escape(feed_def["name"])

    lines = []
    lines.append(f"{cat_emoji} <b>{src_html}</b> · {category_tag}")
    lines.append("")
    lines.append(f"📰 <b>{title_html}</b>")

    if bullets:
        lines.append("")
        lines.append("🧾 Qisqa mazmuni:")
        for b in bullets:
            b = html.escape(b)
            lines.append(f"• {b}")

    lines.append("")
    lines.append(f"🔗 <a href=\"{link_html}\">Manba</a>")

    return "\n".join(lines)


# ============================
#     SEND MESSAGE
# ============================

async def send_post(bot: Bot, text: str):
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print("Xabar yuborishda xato:", e)


# ============================
#     FILE-BASED SEEN IDS
# ============================

def load_seen_ids():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f.readlines())
    except:
        return set()


def save_seen_ids(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        for sid in seen:
            f.write(sid + "\n")


# ============================
#       RSS CHECKER
# ============================

async def check_all_feeds(bot):
    seen_ids = load_seen_ids()

    for feed in RSS_FEEDS:
        url = feed["url"]
        parsed = feedparser.parse(url)

        new_count = 0

        for entry in parsed.entries:
            post_id = getattr(entry, "id", getattr(entry, "link", None))
            if not post_id or post_id in seen_ids:
                continue

            msg = build_message(entry, feed)

            await send_post(bot, msg)

            seen_ids.add(post_id)
            new_count += 1

            if new_count >= MAX_POSTS_PER_FEED:
                break

    save_seen_ids(seen_ids)


# ============================
#        MAIN LOOP
# ============================

async def main():
    bot = Bot(token=TOKEN)

    while True:
        print("🔎 Yangiliklar tekshirilmoqda...")
        await check_all_feeds(bot)
        print("⏳ Kutilmoqda...")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
