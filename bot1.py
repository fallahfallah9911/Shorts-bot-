"""
BOT 1 - SOURCE BOT
------------------
1. Reads source channels from config.yaml
2. Finds new Shorts (ones not uploaded before)
3. Downloads them
4. Uploads to your main YouTube channel
"""

import os
import json
import time
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

SOURCE_CHANNELS   = config["source_channels"]
SHORTS_PER_DAY    = config["shorts_per_day"]
MAIN_CHANNEL      = config["main_channel"]
UPLOAD_DELAY      = config["upload_delay_seconds"]

# ── Tracking file (remembers what's already been uploaded) ──
UPLOADED_LOG = "uploaded_bot1.json"

def load_uploaded():
    if os.path.exists(UPLOADED_LOG):
        with open(UPLOADED_LOG, "r") as f:
            return json.load(f)
    return []

def save_uploaded(uploaded):
    with open(UPLOADED_LOG, "w") as f:
        json.dump(uploaded, f, indent=2)

# ── Get Shorts from a channel's RSS feed ───────────────────
def get_shorts_from_channel(channel_id, already_uploaded):
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    shorts = []

    for entry in feed.entries:
        video_id = entry.get("yt_videoid", "")
        if not video_id:
            continue
        if video_id in already_uploaded:
            continue

        # Check if it's a Short by trying to detect duration via yt-dlp
        url = f"https://www.youtube.com/shorts/{video_id}"
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                duration = info.get("duration", 999)
                if duration <= 60:  # Shorts are 60 seconds or less
                    shorts.append({
                        "video_id": video_id,
                        "url": url,
                        "title": entry.title
                    })
        except Exception as e:
            print(f"  Skipping {video_id}: {e}")
            continue

    return shorts

# ── Download a Short ────────────────────────────────────────
def download_short(url, filename="temp_video.mp4"):
    print(f"  Downloading: {url}")
    ydl_opts = {
        "outtmpl": filename,
        "format": "mp4",
        "quiet": True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"  Downloaded!")

# ── Build YouTube API client ────────────────────────────────
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

    body = {
        "snippet": {
            "title": title,
            "description": "Auto uploaded",
            "categoryId": "22",
            "tags": ["Shorts", "viral", "trending"]
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
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

    video_id = response.get("id")
    print(f"  ✅ Uploaded! https://youtube.com/shorts/{video_id}")
    return video_id

# ── Clean up downloaded file ────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main Bot 1 Logic ────────────────────────────────────────
def run_bot1():
    print("\n========================================")
    print("BOT 1 STARTED — Sourcing Shorts")
    print("========================================\n")

    already_uploaded = load_uploaded()
    uploaded_today = 0

    for channel in SOURCE_CHANNELS:
        if uploaded_today >= SHORTS_PER_DAY:
            print(f"✅ Daily limit of {SHORTS_PER_DAY} Shorts reached. Stopping.")
            break

        print(f"🔍 Checking channel: {channel['name']} ({channel['id']})")
        shorts = get_shorts_from_channel(channel["id"], already_uploaded)

        if not shorts:
            print(f"  No new Shorts found.\n")
            continue

        print(f"  Found {len(shorts)} new Short(s)\n")

        for short in shorts:
            if uploaded_today >= SHORTS_PER_DAY:
                break

            print(f"▶ Processing: {short['title']}")
            try:
                download_short(short["url"])
                upload_to_main(short["title"])
                already_uploaded.append(short["video_id"])
                save_uploaded(already_uploaded)
                uploaded_today += 1
                cleanup()
                print(f"  Waiting {UPLOAD_DELAY}s before next upload...\n")
                time.sleep(UPLOAD_DELAY)
            except Exception as e:
                print(f"  ❌ Error processing {short['title']}: {e}\n")
                cleanup()
                continue

    print(f"\n========================================")
    print(f"BOT 1 DONE — Uploaded {uploaded_today} Short(s) today")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot1()
