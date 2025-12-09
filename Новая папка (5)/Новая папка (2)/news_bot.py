import asyncio
import feedparser
import html
import re
from telegram import Bot

# 🔐 Bot token (o'tgan safargi)
TOKEN = "8383119570:AAGu7FtVxrzcjy81w23MSI9HboVr7QaManA"

# 📢 GigaNews kanal ID (get_id.py bilan topgan edik)
CHANNEL_ID = -1003369735509

# 🌍 Manbalar (RSS)
RSS_FEEDS = {
    # Inglizcha / xalqaro manbalar
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters World": "https://feeds.reuters.com/reuters/worldNews",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "CNN World": "http://rss.cnn.com/rss/edition_world.rss",
    "Bloomberg Markets": "https://feeds.bloomberg.com/market-news.rss",

    # Rus tilidagi manbalar
    "BBC Russian": "https://feeds.bbci.co.uk/russian/rss.xml",
    "RIA Novosti (World)": "https://ria.ru/export/rss2/world/index.xml",
    "TASS": "https://tass.ru/rss/v2.xml",
    "Lenta.ru": "https://lenta.ru/rss/news",
    "Interfax": "https://www.interfax.ru/rss.asp",
}


SEEN_FILE = "seen_ids.txt"


def load_seen_ids():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except FileNotFoundError:
        return set()


def save_seen_ids(ids):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        for _id in ids:
            f.write(_id + "\n")


def clean_html(text):
    text = re.sub(r"<.*?>", "", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def build_message(source_name, entry):
    title = entry.get("title", "Sarlavha yo'q")
    summary = clean_html(entry.get("summary", ""))
    link = entry.get("link", "")

    if len(summary) > 500:
        summary = summary[:500] + "..."

    msg = f"📰 {source_name} | {title}\n\n{summary}"
    if link:
        msg += f"\n\n🔗 Manba: {link}"
    return msg


async def main_loop():
    bot = Bot(TOKEN)
    seen_ids = load_seen_ids()

    while True:
        print("⏳ Yangiliklar tekshirilmoqda...")
        for source, url in RSS_FEEDS.items():
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                entry_id = entry.get("id") or entry.get("link")
                if not entry_id or entry_id in seen_ids:
                    continue

                msg = build_message(source, entry)
                try:
                    await bot.send_message(chat_id=CHANNEL_ID, text=msg)
                    print(f"✔️ Yuborildi: {source} | {entry.get('title')}")
                except Exception as e:
                    print("❌ Xato:", e)

                seen_ids.add(entry_id)
                await asyncio.sleep(2)

        save_seen_ids(seen_ids)
        print("😴 60 sekund kutyapman...\n")
        await asyncio.sleep(60)  # 1 daqiqada bir tekshiradi


if __name__ == "__main__":
    asyncio.run(main_loop())
