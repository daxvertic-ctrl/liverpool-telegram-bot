import feedparser
import requests
import os
import json
import re
import html
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator

# --- تنظیمات ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # مثلاً @YourChannel
RSS_URLS = [
    "https://www.thisisanfield.com/feed/",
    "https://www.liverpoolecho.co.uk/all-about/liverpool%20fc?service=rss"
]
SEEN_FILE = "seen_posts.json"
MAX_POSTS_PER_RUN = 3        # هر بار حداکثر چند پست جدید بفرستد
CAPTION_LIMIT = 1024         # محدودیت تلگرام برای متن زیر عکس
ENGLISH_CHARS = 1500         # چقدر از متن انگلیسی خبر ترجمه شود
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

# آیدی کانال که زیر هر پست نوشته می‌شود (فقط اگر با @ شروع شده باشد)
CHANNEL_TAG = CHANNEL_ID if CHANNEL_ID and CHANNEL_ID.startswith("@") else ""


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def translate(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source="en", target="fa").translate(text[:4500])
    except Exception as e:
        print(f"Translate error: {e}")
        return text


def trim(text, limit):
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    idx = max(cut.rfind(". "), cut.rfind("؟"), cut.rfind("!"))
    if idx > limit * 0.5:
        return cut[: idx + 1]
    return cut.rsplit(" ", 1)[0] + "..."


def entry_image(entry):
    for key in ("media_content", "media_thumbnail"):
        items = entry.get(key)
        if items and items[0].get("url"):
            return items[0]["url"]
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href", "")
    return ""


def fetch_article(link):
    """متن و عکس اصلی خبر را از صفحه‌ی خود خبر می‌گیرد."""
    try:
        r = requests.get(link, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"Could not open article: {e}")
        return "", ""

    soup = BeautifulSoup(r.text, "html.parser")

    image = ""
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        image = og["content"]

    container = soup.find("article") or soup
    text = ""
    for p in container.find_all("p"):
        t = clean(p.get_text(" "))
        if len(t) > 60:
            text += t + " "
        if len(text) >= ENGLISH_CHARS:
            break
    return text.strip(), image


def tg(method, payload):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        print(response.text)
    return response.status_code == 200


def send_post(title_fa, body_fa, image):
    tag = f"\n\n{CHANNEL_TAG}" if CHANNEL_TAG else ""
    room = CAPTION_LIMIT - len(title_fa) - len(tag) - 10
    body_fa = trim(body_fa, room)
    caption = f"<b>{html.escape(title_fa)}</b>\n\n{html.escape(body_fa)}{tag}"

    if image:
        ok = tg("sendPhoto", {
            "chat_id": CHANNEL_ID,
            "photo": image,
            "caption": caption,
            "parse_mode": "HTML"
        })
        if ok:
            return True
        print("Photo failed, sending text only")

    return tg("sendMessage", {
        "chat_id": CHANNEL_ID,
        "text": caption,
        "parse_mode": "HTML"
    })


def main():
    seen = load_seen()
    new_posts = []

    for rss_url in RSS_URLS:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            post_id = entry.get("id") or entry.get("link")
            if post_id and post_id not in seen:
                new_posts.append((
                    post_id,
                    entry.get("title", ""),
                    entry.get("link", ""),
                    entry.get("summary", "") or entry.get("description", ""),
                    entry_image(entry),
                ))

    new_posts = new_posts[:MAX_POSTS_PER_RUN]

    for post_id, title, link, summary, rss_image in reversed(new_posts):
        article_text, page_image = fetch_article(link)
        body_en = article_text or clean(summary)
        image = page_image or rss_image

        title_fa = translate(clean(title))
        body_fa = translate(body_en)

        if send_post(title_fa, body_fa, image):
            seen.add(post_id)
            print(f"Posted: {title}")
        else:
            print(f"Failed to post: {title}")

    save_seen(seen)
    print(f"Done. Total seen posts: {len(seen)}")


if __name__ == "__main__":
    main()
