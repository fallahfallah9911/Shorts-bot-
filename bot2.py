"""
BOT 2 - REPOST BOT (FIXED VERSION)
------------------------------------
1. Detects new Shorts on your main YouTube channel
2. Downloads them
3. Reposts to all 5 YouTube accounts
4. Reposts to all 5 Instagram accounts as Reels
5. If no new video on main channel:
   → Falls back to source channels for unposted videos
   → If source channels have nothing new → uses archive
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
from instagrapi import Client as InstaClient
from instagrapi.exceptions import LoginRequired

# ── Load config ────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

MAIN_CHANNEL    = config["main_channel"]
SOURCE_CHANNELS = config["source_channels"]
YT_ACCOUNTS     = config["youtube_accounts"]
IG_ACCOUNTS     = config["instagram_accounts"]
UPLOAD_DELAY    = config["upload_delay_seconds"]

# ── Tracking files ──────────────────────────────────────────
UPLOADED_LOG = "uploaded_bot2.json"
ARCHIVE_LOG  = "archive_bot2.json"

def load_uploaded():
    if os.path.exists(UPLOADED_LOG):
        with open(UPLOADED_LOG, "r") as f:
            return json.load(f)
    return {}

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

# ── Get Shorts from any channel by ID ──────────────────────
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

# ── Get new Shorts from main channel ───────────────────────
def get_new_shorts_from_main(already_uploaded):
    channel_id = MAIN_CHANNEL["channel_id"]
    return get_shorts_from_channel(channel_id, already_uploaded)

# ── Fallback: get unposted Shorts from source channels ─────
def get_shorts_from_sources(already_uploaded):
    shorts = []
    for channel in SOURCE_CHANNELS:
        print(f"  🔍 Checking source: {channel['name']}")
        found = get_shorts_from_channel(channel["id"], already_uploaded)
        shorts.extend(found)
        if shorts:
            break  # Stop after first source that has content
    return shorts

# ── Download ────────────────────────────────────────────────
def download_short(url, filename="temp_video.mp4"):
    print(f"  Downloading: {url}")
    with yt_dlp.YoutubeDL({"outtmpl": filename, "format": "mp4", "quiet": True}) as ydl:
        ydl.download([url])
    print(f"  Downloaded!")

# ── YouTube upload ──────────────────────────────────────────
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

def upload_to_youtube(account, title, filename="temp_video.mp4"):
    print(f"  📺 Uploading to YouTube: {account['name']}")
    youtube = get_youtube_client(account)
    tags = ["Shorts", "viral", "trending", "food", "japanesefood",
            "asianfood", "foodie", "foodreels", "streetfood", "yummy"]
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
            print(f"    Progress: {int(status.progress() * 100)}%")
    print(f"  ✅ YouTube uploaded!")
    return True

# ── Instagram upload ────────────────────────────────────────
def upload_to_instagram(account, title, filename="temp_video.mp4"):
    print(f"  📸 Uploading to Instagram: {account['name']}")
    cl = InstaClient()
    session_file = f"ig_session_{account['username']}.json"
    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(account["username"], account["password"])
        cl.dump_settings(session_file)
    except LoginRequired:
        cl.login(account["username"], account["password"])
        cl.dump_settings(session_file)
    except Exception as e:
        print(f"  ❌ Instagram login failed for {account['name']}: {e}")
        return False
    try:
        caption = f"{title}\n\n🍱 Amazing food content!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Foodie #FoodReels #StreetFood #Yummy #Trending #Reels"
        cl.clip_upload(filename, caption=caption)
        print(f"  ✅ Instagram Reel uploaded!")
        return True
    except Exception as e:
        print(f"  ❌ Instagram upload failed: {e}")
        return False

# ── Cleanup ─────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Process one short to all accounts ──────────────────────
def process_short(short, uploaded_log, archive):
    video_id = short["video_id"]
    print(f"\n▶ Processing: {short['title']}")

    try:
        download_short(short["url"])
    except Exception as e:
        print(f"  ❌ Download failed: {e}\n")
        return

    uploaded_log[video_id] = {"title": short["title"], "accounts": []}

    # Upload to all YouTube accounts
    print(f"\n  📺 Uploading to YouTube accounts...")
    for account in YT_ACCOUNTS:
        try:
            upload_to_youtube(account, short["title"])
            uploaded_log[video_id]["accounts"].append(account["name"])
        except Exception as e:
            print(f"  ❌ Failed for {account['name']}: {e}")
        time.sleep(UPLOAD_DELAY)

    # Upload to all Instagram accounts
    print(f"\n  📸 Uploading to Instagram accounts...")
    for account in IG_ACCOUNTS:
        try:
            upload_to_instagram(account, short["title"])
            uploaded_log[video_id]["accounts"].append(account["name"])
        except Exception as e:
            print(f"  ❌ Failed for {account['name']}: {e}")
        time.sleep(UPLOAD_DELAY)

    # Save to archive
    if not any(v["video_id"] == video_id for v in archive):
        archive.append(short)
        save_archive(archive)

    save_uploaded(uploaded_log)
    cleanup()
    print(f"\n  ✅ Done with: {short['title']}\n")

# ── Main ────────────────────────────────────────────────────
def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting Shorts")
    print("========================================\n")

    uploaded_log = load_uploaded()
    archive = load_archive()
    short_to_post = None

    # Step 1: Check main channel for new uploads
    print(f"🔍 Checking main channel for new Shorts...")
    new_shorts = get_new_shorts_from_main(uploaded_log)

    if new_shorts:
        print(f"  ✅ Found {len(new_shorts)} new Short(s) on main channel!\n")
        short_to_post = new_shorts[0]

    # Step 2: Fallback to source channels
    else:
        print("  No new Shorts on main channel.")
        print("\n🔍 Checking source channels for unposted videos...")
        source_shorts = get_shorts_from_sources(uploaded_log)

        if source_shorts:
            print(f"  ✅ Found {len(source_shorts)} video(s) from source channels!\n")
            short_to_post = source_shorts[0]

        # Step 3: Last resort — use archive
        else:
            print("  No new videos in source channels either.")
            if archive:
                print("\n  📦 Using random archive video as last resort...\n")
                short_to_post = random.choice(archive)
            else:
                print("\n  ⚠️ Archive is also empty. Nothing to post.")

    if short_to_post:
        process_short(short_to_post, uploaded_log, archive)

    print(f"\n========================================")
    print(f"BOT 2 DONE — All accounts updated!")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot2()
