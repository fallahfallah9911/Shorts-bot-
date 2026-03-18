"""
BOT 2 - REPOST BOT
------------------
1. Detects new Shorts on your main YouTube channel
2. Downloads them
3. Reposts to all 5 YouTube accounts
4. Reposts to all 5 Instagram accounts as Reels
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
from instagrapi import Client as InstaClient
from instagrapi.exceptions import LoginRequired

# ── Load config ────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

MAIN_CHANNEL       = config["main_channel"]
YT_ACCOUNTS        = config["youtube_accounts"]
IG_ACCOUNTS        = config["instagram_accounts"]
UPLOAD_DELAY       = config["upload_delay_seconds"]

# ── Tracking file ───────────────────────────────────────────
UPLOADED_LOG = "uploaded_bot2.json"

def load_uploaded():
    if os.path.exists(UPLOADED_LOG):
        with open(UPLOADED_LOG, "r") as f:
            return json.load(f)
    return {}

def save_uploaded(uploaded):
    with open(UPLOADED_LOG, "w") as f:
        json.dump(uploaded, f, indent=2)

# ── Get new Shorts from main channel ───────────────────────
def get_new_shorts_from_main(already_uploaded):
    channel_id = MAIN_CHANNEL["channel_id"]
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    new_shorts = []

    for entry in feed.entries:
        video_id = entry.get("yt_videoid", "")
        if not video_id or video_id in already_uploaded:
            continue
        url = f"https://www.youtube.com/shorts/{video_id}"
        try:
            with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
                duration = info.get("duration", 999)
                if duration <= 60:
                    new_shorts.append({
                        "video_id": video_id,
                        "url": url,
                        "title": entry.title
                    })
        except Exception as e:
            print(f"  Skipping {video_id}: {e}")
            continue

    return new_shorts

# ── Download Short ──────────────────────────────────────────
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
            print(f"    Upload progress: {int(status.progress() * 100)}%")

    video_id = response.get("id")
    print(f"  ✅ YouTube uploaded! https://youtube.com/shorts/{video_id}")
    return True

# ── Instagram upload ────────────────────────────────────────
def upload_to_instagram(account, title, filename="temp_video.mp4"):
    print(f"  📸 Uploading to Instagram: {account['name']}")
    cl = InstaClient()

    # Session file to avoid logging in every time
    session_file = f"ig_session_{account['username']}.json"

    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
            cl.login(account["username"], account["password"])
        else:
            cl.login(account["username"], account["password"])
            cl.dump_settings(session_file)
    except LoginRequired:
        print(f"    Re-logging in to {account['username']}")
        cl.login(account["username"], account["password"])
        cl.dump_settings(session_file)
    except Exception as e:
        print(f"  ❌ Instagram login failed for {account['name']}: {e}")
        return False

    try:
        caption = f"{title}\n\n#Shorts #Reels #Viral #Trending"
        cl.clip_upload(filename, caption=caption)
        print(f"  ✅ Instagram Reel uploaded for {account['name']}!")
        return True
    except Exception as e:
        print(f"  ❌ Instagram upload failed for {account['name']}: {e}")
        return False

# ── Clean up ────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main Bot 2 Logic ────────────────────────────────────────
def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting Shorts")
    print("========================================\n")

    uploaded_log = load_uploaded()

    print(f"🔍 Checking main channel for new Shorts...")
    new_shorts = get_new_shorts_from_main(uploaded_log)

    if not new_shorts:
        print("  No new Shorts found on main channel. Nothing to repost.\n")
        return

    print(f"  Found {len(new_shorts)} new Short(s)!\n")

    for short in new_shorts:
        print(f"\n▶ Processing: {short['title']}")
        video_id = short["video_id"]
        uploaded_log[video_id] = {"title": short["title"], "accounts": []}

        try:
            download_short(short["url"])
        except Exception as e:
            print(f"  ❌ Failed to download: {e}\n")
            continue

        # Track how many uploaded today per account
        yt_count  = {acc["name"]: 0 for acc in YT_ACCOUNTS}
        ig_count  = {acc["name"]: 0 for acc in IG_ACCOUNTS}

        # ── Upload to all YouTube accounts ──
        print(f"\n  📺 Uploading to YouTube accounts...")
        for account in YT_ACCOUNTS:
            if yt_count[account["name"]] >= account["shorts_per_day"]:
                print(f"  ⏭ {account['name']} daily limit reached, skipping.")
                continue
            try:
                success = upload_to_youtube(account, short["title"])
                if success:
                    yt_count[account["name"]] += 1
                    uploaded_log[video_id]["accounts"].append(account["name"])
            except Exception as e:
                print(f"  ❌ Failed for {account['name']}: {e}")
            print(f"  Waiting {UPLOAD_DELAY}s...")
            time.sleep(UPLOAD_DELAY)

        # ── Upload to all Instagram accounts ──
        print(f"\n  📸 Uploading to Instagram accounts...")
        for account in IG_ACCOUNTS:
            if ig_count[account["name"]] >= account["reels_per_day"]:
                print(f"  ⏭ {account['name']} daily limit reached, skipping.")
                continue
            try:
                success = upload_to_instagram(account, short["title"])
                if success:
                    ig_count[account["name"]] += 1
                    uploaded_log[video_id]["accounts"].append(account["name"])
            except Exception as e:
                print(f"  ❌ Failed for {account['name']}: {e}")
            print(f"  Waiting {UPLOAD_DELAY}s...")
            time.sleep(UPLOAD_DELAY)

        save_uploaded(uploaded_log)
        cleanup()
        print(f"\n  ✅ Done with: {short['title']}\n")

    print(f"\n========================================")
    print(f"BOT 2 DONE — All accounts updated!")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot2()
