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
    # 🌍 World
    {"name": "BBC World",        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",        "category": "world"},
    {"name": "Reuters World",    "url": "https://feeds.reuters.com/reuters/worldNews",        "category": "world"},
    {"name": "Al Jazeera",       "url": "https://www.aljazeera.com/xml/rss/all.xml",          "category": "world"},
    {"name": "CNN World",        "url": "http://rss.cnn.com/rss/edition_world.rss",           "category": "world"},
    {"name": "Bloomberg Markets","url": "https://feeds.bloomberg.com/market-news.rss",        "category": "economy"},

    # 🇷🇺 Russian
    {"name": "BBC Russian",      "url": "https://feeds.bbci.co.uk/russian/rss.xml",           "category": "russian"},
    {"name": "RIA Novosti",      "url": "https://ria.ru/export/rss2/world/index.xml",         "category": "russian"},
    {"name": "TASS",             "url": "https://tass.ru/rss/v2.xml",                         "category": "russian"},
    {"name": "Lenta.ru",         "url": "https://lenta.ru/rss/news",                          "category": "russian"},
    {"name": "Interfax",         "url": "https://www.interfax.ru/rss.asp",                    "category": "russian"},

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
    """Kategoriya tagi + manba + sarlavha + linkdan iborat post matni."""
    category_key = feed_def.get("category", "other")
    category_tag = CATEGORIES.get(category_key, CATEGORIES["other"])

    title = clean_html(getattr(entry, "title", ""))
    summary = clean_html(getattr(entry, "summary", ""))

    # Sarlavha bo'lmasa ham bo'sh qolmasin
    if not title:
        title = "(Sarlavhasiz yangilik)"

    link = getattr(entry, "link", "") or getattr(entry, "id", "")

    # Qisqa summary (optimallashtirish)
    if summary and len(summary) > 300:
        summary = summary[:300] + "..."

    source_tag = f"[{feed_def['name']}]"

    parts = [
        f"{category_tag} {source_tag}",
        "",
        title,
    ]
    if summary:
        parts.append("")
        parts.append(summary)
    if link:
        parts.append("")
        parts.append(link)

    return "\n".join(parts)


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
    """Kanalga xabar yuborish."""
    try:
        await bot.send_message(chat_id=CHANNEL_ID, text=text)
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
