"""
BOT 1 - SOURCE BOT (FINAL VERSION)
------------------------------------
1. Reads source channels from config.yaml
2. Finds new Shorts (ones not uploaded before)
3. Downloads them
4. Uploads to your main YouTube channel
5. If no new Shorts found → uploads a random old one
6. Optimized for US audience
"""

import os
import json
import time
import random
import yt_dlp
import yaml
import feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── Load config ────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
SHORTS_PER_DAY  = config["shorts_per_day"]
MAIN_CHANNEL    = config["main_channel"]
UPLOAD_DELAY    = config["upload_delay_seconds"]

# ── Tracking files ──────────────────────────────────────────
UPLOADED_LOG = "uploaded_bot1.json"
ARCHIVE_LOG  = "archive_bot1.json"

def load_uploaded():
    if os.path.exists(UPLOADED_LOG):
        with open(UPLOADED_LOG, "r") as f:
            return json.load(f)
    return []

def save_uploaded(uploaded):
    with open(UPLOADED_LOG, "w") as f:
        json.dump(uploaded, f, indent=2)

def load_archive():
    if os.path.exists(ARCHIVE_LOG):
        with open(ARCHIVE_LOG, "r") as f:
            return json.load(f)
    return []

def save_archive(archive):
    with open(ARCHIVE_LOG, "w") as f:
        json.dump(archive, f, indent=2)

# ── Get Shorts from a channel's RSS feed ───────────────────
def get_shorts_from_channel(channel_id, already_uploaded):
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    shorts = []

    for entry in feed.entries:
        video_id = entry.get("yt_videoid", "")
        if not video_id or video_id in already_uploaded:
            continue
        url = f"https://www.youtube.com/shorts/{video_id}"
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if info.get("duration", 999) <= 60:
                    shorts.append({
                        "video_id": video_id,
                        "url": url,
                        "title": entry.title
                    })
        except Exception as e:
            print(f"  Skipping {video_id}: {e}")
    return shorts

# ── Download ────────────────────────────────────────────────
def download_short(url, filename="temp_video.mp4"):
    print(f"  Downloading: {url}")
    with yt_dlp.YoutubeDL({"outtmpl": filename, "format": "mp4", "quiet": True}) as ydl:
        ydl.download([url])
    print(f"  Downloaded!")

# ── YouTube client ──────────────────────────────────────────
def get_youtube_client(account):
    creds = Credentials(
        token=None,
        refresh_token=account["refresh_token"],
        client_id=account["client_id"],
        client_secret=account["client_secret"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

# ── Upload to main channel ──────────────────────────────────
def upload_to_main(title, filename="temp_video.mp4"):
    print(f"  Uploading to main channel: {title}")
    youtube = get_youtube_client(MAIN_CHANNEL)
    tags = ["Shorts", "viral", "trending", "food", "japanesefood",
            "asianfood", "foodie", "foodreels", "streetfood", "yummy",
            "foodvideo", "viralreels", "shortsvideo"]
    body = {
        "snippet": {
            "title": title,
            "description": "🍱 Amazing food content!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Foodie #FoodReels #StreetFood",
            "categoryId": "22",
            "tags": tags,
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(filename, chunksize=-1, resumable=True)
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Upload progress: {int(status.progress() * 100)}%")
    print(f"  ✅ Uploaded! https://youtube.com/shorts/{response.get('id')}")

# ── Cleanup ─────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Fallback: upload random old video ──────────────────────
def upload_old_video():
    archive = load_archive()
    if not archive:
        print("  ⚠️ No archive videos yet. Skipping.")
        return False
    old_video = random.choice(archive)
    print(f"  📦 Using archive video: {old_video['title']}")
    try:
        download_short(old_video["url"])
        upload_to_main(old_video["title"])
        cleanup()
        return True
    except Exception as e:
        print(f"  ❌ Archive upload failed: {e}")
        cleanup()
        return False

# ── Main ────────────────────────────────────────────────────
def run_bot1():
    print("\n========================================")
    print("BOT 1 STARTED — Sourcing Shorts")
    print("========================================\n")

    already_uploaded = load_uploaded()
    archive = load_archive()
    uploaded_today = 0
    found_new = False

    for channel in SOURCE_CHANNELS:
        if uploaded_today >= SHORTS_PER_DAY:
            break

        print(f"🔍 Checking: {channel['name']}")
        shorts = get_shorts_from_channel(channel["id"], already_uploaded)

        if not shorts:
            print(f"  No new Shorts.\n")
            continue

        found_new = True
        for short in shorts:
            if uploaded_today >= SHORTS_PER_DAY:
                break
            print(f"▶ Processing: {short['title']}")
            try:
                download_short(short["url"])
                upload_to_main(short["title"])
                already_uploaded.append(short["video_id"])
                save_uploaded(already_uploaded)
                if not any(v["video_id"] == short["video_id"] for v in archive):
                    archive.append(short)
                    save_archive(archive)
                uploaded_today += 1
                cleanup()
                time.sleep(UPLOAD_DELAY)
            except Exception as e:
                print(f"  ❌ Error: {e}\n")
                cleanup()

    # Fallback if no new videos found
    if not found_new and uploaded_today < SHORTS_PER_DAY:
        print("\n⚠️ No new Shorts! Using archive...\n")
        for _ in range(SHORTS_PER_DAY - uploaded_today):
            if upload_old_video():
                uploaded_today += 1
            time.sleep(UPLOAD_DELAY)

    print(f"\n========================================")
    print(f"BOT 1 DONE — Uploaded {uploaded_today} Short(s)")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot1()
