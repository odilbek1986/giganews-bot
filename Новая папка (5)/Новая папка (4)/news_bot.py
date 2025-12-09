import asyncio
import feedparser
import html
import re
from concurrent.futures import ThreadPoolExecutor
from telegram import Bot

# ==============================
#   BU YERNI O'ZINGGA MOSLA
# ==============================

TOKEN = "8383119570:AAGu7FtVxrzcjy81w23MSI9HboVr7QaManA"          # BotFather bergan token
CHANNEL_ID = -1003369735509               # GigaNews kanal ID (senikini qo'y)

SEEN_FILE = "seen_ids.txt"                 # yangi ID lar shu faylda saqlanadi
CHECK_INTERVAL = 600                       # necha sekundda bir tekshirish (600 = 10 daqiqa)

# -------------------------------
#   KATEGORIYALAR VA TAGLAR
# -------------------------------
CATEGORIES = {
    "world":   "#World",
    "russian": "#Russia",
    "uzbek":   "#Uzbek",
    "economy": "#Economy",
    "other":   "#News",
}

# -------------------------------
#   RSS MANBALAR (BO'LIMLAR BILAN)
#   category: world / russian / uzbek / economy / other
# -------------------------------

RSS_FEEDS = [
    # 🇷🇺 Russian TOP
    {"name": "BBC Russian",  "url": "https://feeds.bbci.co.uk/russian/rss.xml",           "category": "russian"},
    {"name": "Lenta.ru",     "url": "https://lenta.ru/rss/news",                          "category": "russian"},
    {"name": "Interfax",     "url": "https://www.interfax.ru/rss.asp",                    "category": "russian"},

    # 🌍 English / World TOP
    {"name": "BBC World",    "url": "https://feeds.bbci.co.uk/news/world/rss.xml",        "category": "world"},
    {"name": "CNN World",    "url": "http://rss.cnn.com/rss/edition_world.rss",           "category": "world"},
    {"name": "Reuters World","url": "https://feeds.reuters.com/reuters/worldNews",        "category": "world"},

    # 🇺🇿 Uzbek — keyin parser yozamiz, hozircha RSS yo'q, shuning uchun bo'sh.
    # {"name": "Daryo.uz",       "url": "https://daryo.uz/rss",                 "category": "uzbek"},
    # {"name": "Gazeta.uz",      "url": "https://www.gazeta.uz/ru/rss",         "category": "uzbek"},
]

# ==============================
#   YORDAMCHI FUNKSIYALAR
# ==============================

def load_seen_ids() -> set:
    """Yangi bo'lmagan (oldin yuborilgan) yangilik ID larini fayldan o'qish."""
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_ids(ids: set):
    """Ko'rilgan ID larni faylga yozish."""
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        for _id in ids:
            f.write(_id + "\n")


def clean_html(text: str) -> str:
    """HTML teglar va entitylarni tozalash."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_message(entry, feed_def) -> str:
    """Chiroyli format: emoji + manba + hashtag + sarlavha + qisqa izoh + link."""

    category_key = feed_def.get("category", "other")
    category_tag = CATEGORIES.get(category_key, CATEGORIES["other"])

    # Kategoriya bo'yicha emoji
    cat_emoji_map = {
        "world": "🌍",
        "russian": "🇷🇺",
        "uzbek": "🇺🇿",
        "economy": "💰",
        "other": "🛰",
    }
    cat_emoji = cat_emoji_map.get(category_key, "🛰")

    title = clean_html(getattr(entry, "title", "") or "")
    summary = clean_html(getattr(entry, "summary", "") or "")
    link = getattr(entry, "link", "") or getattr(entry, "id", "")

    if not title:
        title = "(Sarlavhasiz yangilik)"

    # 1 ta gap + qisqartirish
    if summary:
        parts = re.split(r"[.!?]", summary)
        first_sentence = parts[0].strip()
        summary = first_sentence
        max_len = globals().get("SUMMARY_MAX_CHARS", 180)
        if len(summary) > max_len:
            summary = summary[:max_len] + "..."

    # HTML uchun escape
    source_name = html.escape(feed_def["name"])
    title_html = html.escape(title)
    summary_html = html.escape(summary) if summary else ""
    link_html = html.escape(link) if link else ""

    lines = [
        f"{cat_emoji} <b>{source_name}</b> · {category_tag}",
        "",
        f"<b>{title_html}</b>",
    ]

    if summary_html:
        lines.append("")
        lines.append(summary_html)

    if link_html:
        lines.append("")
        lines.append(f'<a href="{link_html}">🔗 Читать полностью</a>')

    return "\n".join(lines)

# ==============================
#   ASINXRON QISM (TEZLIK UCHUN)
# ==============================

# feedparser sinxron, shuning uchun uni alohida thread-larda ishlatamiz
executor = ThreadPoolExecutor(max_workers=5)


async def fetch_feed_async(url: str):
    """feedparser.parse ni fon threadda ishga tushirish."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, feedparser.parse, url)


async def send_post(bot: Bot, text: str):
    """Kanalga xabar yuborish (HTML formatda)."""
    try:
        await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=False,  # istasang True qilib, link previewni o'chirishing mumkin
        )
    except Exception as e:
        print("Xabar yuborishda xato:", e)
async def check_all_feeds(bot: Bot, seen_ids: set):
    """Barcha RSS manbalarni tekshirish (parallel tarzda)."""
    print("🔎 Yangiliklar tekshirilmoqda...")

    # 1) Barcha feedlarni parallel o'qiymiz
    tasks = [fetch_feed_async(feed["url"]) for feed in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 2) Natijalarni ko'rib chiqamiz
    for feed_def, result in zip(RSS_FEEDS, results):
        name = feed_def["name"]

        if isinstance(result, Exception):
            print(f"⚠️ {name} uchun xato:", result)
            continue

        feed = result
        entries = getattr(feed, "entries", [])

        print(f"✅ {name}: {len(entries)} ta maqola topildi")

        # Har bir manbadan juda ko'p bo'lmasin, masalan 3 ta yangilik
        new_count = 0

        for entry in entries:
            entry_id = getattr(entry, "id", None) or getattr(entry, "link", None)
            if not entry_id:
                continue

            if entry_id in seen_ids:
                continue  # allaqachon yuborilgan

            message = build_message(entry, feed_def)
            await send_post(bot, message)

            seen_ids.add(entry_id)
            new_count += 1

            # Har bir manbadan maksimal necha ta yangilik yuborish
            if new_count >= 3:
                break

        if new_count:
            print(f"➕ {name} uchun {new_count} ta yangi post yuborildi")
        else:
            print(f"— {name} uchun yangi narsa yo'q")


async def main():
    bot = Bot(TOKEN)
    seen_ids = load_seen_ids()
    print("Bot ishga tushdi. GigaNews kuzatuvda 👀")

    while True:
        await check_all_feeds(bot, seen_ids)
        save_seen_ids(seen_ids)
        print(f"⏳ {CHECK_INTERVAL // 60} daqiqadan keyin yana tekshiraman...\n")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
