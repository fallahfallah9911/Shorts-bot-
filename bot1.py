"""
BOT 1 - MAIN CHANNEL BOT
Reads from drive_library.json (built by Bot 0).
Downloads video from Google Drive.
Uploads to main YouTube channel.
Marks video as used.
"""

import os, json, time, random, yt_dlp, yaml, isodate
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── Config ─────────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

UPLOAD_DELAY = config.get("upload_delay_seconds", 30)
MAX_RETRIES  = 3
RETRY_WAIT   = 30

# ── Credentials ────────────────────────────────────────────
MAIN_CHANNEL = {
    "channel_id":    os.environ.get("MAIN_CHANNEL_ID", "UCqsyePuDbG_GdWgr38CiaBg"),
    "client_id":     os.environ["MAIN_CLIENT_ID"],
    "client_secret": os.environ["MAIN_CLIENT_SECRET"],
    "refresh_token": os.environ["MAIN_REFRESH_TOKEN"],
}

# ── Log files ──────────────────────────────────────────────
LIBRARY_FILE = "drive_library.json"

def load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"  ⚠️ Could not load {path}: {e}")
    return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  ⚠️ Could not save {path}: {e}")

# ── YouTube client ─────────────────────────────────────────
def get_youtube_client():
    creds = Credentials(
        token=None,
        refresh_token=MAIN_CHANNEL["refresh_token"],
        client_id=MAIN_CHANNEL["client_id"],
        client_secret=MAIN_CHANNEL["client_secret"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)

# ── Download from Drive link with retry ───────────────────
def download_from_drive(drive_link, title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Downloading from Drive (attempt {attempt}/{MAX_RETRIES}): {title}")
        try:
            if os.path.exists(filename):
                os.remove(filename)
            ydl_opts = {
                "outtmpl": filename,
                "quiet": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([drive_link])
            if not os.path.exists(filename):
                raise FileNotFoundError("File not found after download")
            print(f"  Downloaded: {os.path.getsize(filename)} bytes")
            return True
        except Exception as e:
            print(f"  ⚠️ Drive download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Drive download: {title}")
    return False

# ── Upload to main channel with retry ─────────────────────
def upload_to_main(title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Uploading to main channel (attempt {attempt}/{MAX_RETRIES}): {title}")
        try:
            yt = get_youtube_client()
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": "🍱 Amazing food content!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Foodie #StreetFood",
                    "categoryId": "22",
                    "tags": ["Shorts", "viral", "food", "japanesefood", "asianfood", "foodie", "streetfood"],
                    "defaultLanguage": "en",
                    "defaultAudioLanguage": "en"
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }
            req = yt.videos().insert(
                part="snippet,status",
                body=body,
                media_body=MediaFileUpload(filename, chunksize=-1, resumable=True)
            )
            response = None
            while response is None:
                status, response = req.next_chunk()
                if status:
                    print(f"  Upload progress: {int(status.progress() * 100)}%")
            video_id = response.get("id", "unknown")
            print(f"  ✅ Uploaded: https://youtube.com/watch?v={video_id}")
            return video_id
        except Exception as e:
            print(f"  ⚠️ Upload attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Upload to main channel")
    return None

# ── Cleanup ────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)
        print(f"  Cleaned up {filename}")

# ── Main ───────────────────────────────────────────────────
def run_bot1():
    print("\n========================================")
    print("BOT 1 STARTED — Uploading to Main Channel")
    print("========================================\n")

    library = load_json(LIBRARY_FILE, [])

    if not library:
        print("⚠️ Drive library is empty. Bot 0 needs to run first.")
        print("========================================\n")
        return

    # Get unused videos
    unused = [v for v in library if not v.get("used")]
    print(f"  {len(unused)} unused video(s) in library")

    if not unused:
        print("⚠️ No unused videos left in library. Waiting for Bot 0 to refresh.")
        print("========================================\n")
        return

    # Pick the oldest unused video (first in list)
    video = unused[0]
    print(f"\n▶ Selected: {video['title']}")

    # Download from Drive
    if not download_from_drive(video["drive_link"], video["title"]):
        cleanup()
        print("========================================\n")
        return

    # Upload to main channel
    uploaded_id = upload_to_main(video["title"])
    cleanup()

    if uploaded_id:
        # Mark as used and save the uploaded YT video ID for bot2
        for v in library:
            if v["video_id"] == video["video_id"]:
                v["used"] = True
                v["main_channel_video_id"] = uploaded_id
                break
        save_json(LIBRARY_FILE, library)
        print(f"\n  ✅ Marked as used in library")
    else:
        print(f"\n  ❌ Upload failed, video stays in library for retry")

    print(f"\n========================================")
    print(f"BOT 1 DONE")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot1()
