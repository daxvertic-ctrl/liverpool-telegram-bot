import feedparser
import requests
import os
import json
import re
import html

# --- تنظیمات ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")  # مثلاً @YourChannel یا -100xxxxxxxxxx
RSS_URLS = [
    "https://www.thisisanfield.com/feed/",
    "https://www.liverpoolecho.co.uk/all-about/liverpool%20fc?service=rss"
]
SEEN_FILE = "seen_posts.json"
MAX_POSTS_PER_RUN = 3  # هر بار حداکثر چند پست جدید بفرستد


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


def clean(text):
    # حذف همه تگ‌های HTML و تمیز کردن متن
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def send_to_telegram(title, link, summary=""):
    title = html.escape(clean(title))
    summary = html.escape(clean(summary)[:300])

    text = f"<b>{title}</b>\n\n"
    if summary:
        text += f"{summary}...\n\n"
    text += f'<a href="{link}">ادامه مطلب</a>'

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    response = requests.post(url, json=payload, timeout=30)
    if response.status_code != 200:
        print(response.text)
    return response.status_code == 200


def main():
    seen = load_seen()
    new_posts = []

    for rss_url in RSS_URLS:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            post_id = entry.get("id") or entry.get("link")
            if post_id and post_id not in seen:
                title = entry.get("title", "بدون عنوان")
                link = entry.get("link", "")
                summary = entry.get("summary", "") or entry.get("description", "")
                new_posts.append((post_id, title, link, summary))

    # جدیدترین‌ها را اول بفرست
    new_posts = new_posts[:MAX_POSTS_PER_RUN]

    for post_id, title, link, summary in reversed(new_posts):
        if send_to_telegram(title, link, summary):
            seen.add(post_id)
            print(f"Posted: {title}")
        else:
            print(f"Failed to post: {title}")

    save_seen(seen)
    print(f"Done. Total seen posts: {len(seen)}")


if __name__ == "__main__":
    main()
