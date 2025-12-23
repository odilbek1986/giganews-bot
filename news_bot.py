# news_bot.py
import time
import logging
import re
from html import escape

import feedparser
import httpx
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading


# =====================
#   SOZLAMALAR
# =====================

BOT_TOKEN = "8383119570:AAGu7FtVxrzcjy81w23MSI9HboVr7QaManA"
TARGET_CHAT_ID = -1003369735509

POST_INTERVAL_SECONDS = 20 * 60  # 20 daqiqa


RSS_FEEDS = {
    "Kun.uz": "https://kun.uz/news/rss",
    "Lenta.ru": "https://lenta.ru/rss/news",
    "BBC": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Reuters": "http://feeds.reuters.com/Reuters/worldNews",
}

PER_SOURCE_LIMITS = {
    "Kun.uz": 5,
    "Lenta.ru": 2,
    "BBC": 3,
    "Reuters": 3,
}

sent_links: set[str] = set()



# =====================
#   YORDAMCHI FUNKSIYALAR
# =====================

def extract_lenta_image(summary_html: str) -> str | None:
    if not summary_html:
        return None
    match = re.search(r'<img[^>]+src="([^"]+)"', summary_html)
    return match.group(1) if match else None


def extract_kunuz_image(article_url: str) -> str | None:
    try:
        resp = httpx.get(article_url, timeout=10.0, follow_redirects=True)
        html = resp.text
    except Exception as e:
        logging.error(f"Kun.uz sahifasini yuklashda xato: {e}")
        return None

    m1 = re.search(r'<div class="news-img".*?<img[^>]+src="([^"]+)"', html, re.S)
    if m1:
        url = m1.group(1)
    else:
        m2 = re.search(r'<meta property="og:image" content="([^"]+)"', html)
        if not m2:
            return None
        url = m2.group(1)

    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://kun.uz" + url

    return url


def extract_image_url(entry, source_name: str) -> str | None:
    media_content = entry.get("media_content") or entry.get("media:content")
    if isinstance(media_content, list) and media_content:
        if media_content[0].get("url"):
            return media_content[0]["url"]

    media_thumb = entry.get("media_thumbnail") or entry.get("media:thumbnail")
    if isinstance(media_thumb, list) and media_thumb:
        if media_thumb[0].get("url"):
            return media_thumb[0]["url"]

    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image/"):
            return link.get("href")

    if source_name == "Lenta.ru":
        img = extract_lenta_image(entry.get("summary") or "")
        if img:
            return img

    if source_name == "Kun.uz":
        link = entry.get("link") or ""
        if link:
            img = extract_kunuz_image(link)
            if img:
                return img

    return None



# =====================
#    RSS FETCH
# =====================

def fetch_rss_items() -> list[dict]:
    items: list[dict] = []

    for source_name, url in RSS_FEEDS.items():
        feed = feedparser.parse(url)
        limit = PER_SOURCE_LIMITS.get(source_name, 5)

        for entry in feed.entries[:limit]:
            link = entry.get("link")
            if not link:
                continue

            if link in sent_links:
                continue
            sent_links.add(link)

            image_url = extract_image_url(entry, source_name)

            items.append({
                "source": source_name,
                "title": (entry.get("title") or "").strip(),
                "summary": (entry.get("summary") or "").strip(),
                "link": link,
                "published": (entry.get("published") or "").strip(),
                "image_url": image_url,
            })

    return items



# =====================
#    CAPTION FORMAT
# =====================

def format_caption(item: dict) -> str:
    title = escape(item.get("title", ""))
    source = escape(item.get("source", ""))
    summary_raw = (item.get("summary") or "").strip().replace("\n", " ")
    summary = escape(summary_raw)
    link = item.get("link")
    published = item.get("published")

    lines = []

    lines.append(f"📰 <b>{title}</b>")

    if source:
        lines.append(f"🌐 Manba: {source}")
    if published:
        lines.append(f"🕒 {published}")

    if summary:
        short = summary[:350]
        if len(summary) > 350:
            short = short.rsplit(" ", 1)[0] + "..."
        lines.append("")
        lines.append(f"🧾 {short}")

    tag = source.lower().replace(".", "").replace(" ", "")
    lines.append("")
    lines.append(f"#{tag} #giganews")

    return "\n".join(lines)



# =====================
#    TELEGRAMGA YUBORISH
# =====================

def send_photo_with_caption(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        httpx.post(url, json={
            "chat_id": TARGET_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        }, timeout=30.0)
    except Exception as e:
        logging.error(f"sendPhoto xato: {e}")


def send_text_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        httpx.post(url, json={
            "chat_id": TARGET_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=30.0)
    except Exception as e:
        logging.error(f"sendMessage xato: {e}")



# =====================
#     ASOSIY LOOP
# =====================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        return


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    logging.info("GigaNews bot ishga tushdi. Yangiliklarni yig‘ishni boshladim.")

    while True:
        try:
            items = fetch_rss_items()
            if items:
                logging.info(f"{len(items)} ta yangilik yuborilyapti...")
                for item in items:
                    caption = format_caption(item)
                    if item.get("image_url"):
                        send_photo_with_caption(item["image_url"], caption)
                    else:
                        send_text_message(caption)
                    time.sleep(1)
            else:
                logging.info("Yangilik topilmadi.")
        except Exception as e:
            logging.error(f"Loop xato: {e}")

        time.sleep(POST_INTERVAL_SECONDS)



def run_server():
    port = int(os.environ.get("PORT", "8000"))
    server = HTTPServer(("", port), HealthHandler)
    print(f"Health server {port} portda ishlayapti...")
    server.serve_forever()



if __name__ == "__main__":
    threading.Thread(target=main, daemon=True).start()
    run_server()
