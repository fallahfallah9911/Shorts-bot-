"""
BOT 2 - REPOST BOT
Reads the latest used video from drive_library.json (posted by Bot 1).
Downloads from Google Drive.
Reposts to 5 YouTube accounts + 5 Instagram accounts.
Includes retry logic and verification summary.
"""

import os, json, time, random, yt_dlp, yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

try:
    from instagrapi import Client as InstaClient
    INSTAGRAM_AVAILABLE = True
except ImportError:
    INSTAGRAM_AVAILABLE = False
    print("⚠️ instagrapi not available - Instagram uploads disabled")

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

YT_ACCOUNTS = [
    {"name": "Ytfall1", "client_id": os.environ["YT1_CLIENT_ID"], "client_secret": os.environ["YT1_CLIENT_SECRET"], "refresh_token": os.environ["YT1_REFRESH_TOKEN"]},
    {"name": "Ytfall2", "client_id": os.environ["YT2_CLIENT_ID"], "client_secret": os.environ["YT2_CLIENT_SECRET"], "refresh_token": os.environ["YT2_REFRESH_TOKEN"]},
    {"name": "Ytfall3", "client_id": os.environ["YT3_CLIENT_ID"], "client_secret": os.environ["YT3_CLIENT_SECRET"], "refresh_token": os.environ["YT3_REFRESH_TOKEN"]},
    {"name": "Ytfall4", "client_id": os.environ["YT4_CLIENT_ID"], "client_secret": os.environ["YT4_CLIENT_SECRET"], "refresh_token": os.environ["YT4_REFRESH_TOKEN"]},
    {"name": "Ytfall5", "client_id": os.environ["YT5_CLIENT_ID"], "client_secret": os.environ["YT5_CLIENT_SECRET"], "refresh_token": os.environ["YT5_REFRESH_TOKEN"]},
]

IG_ACCOUNTS = []
ig_configs = [
    ("japanese_foodhouse", "IG1_PASSWORD"),
    ("tokyo.food.daily",   "IG2_PASSWORD"),
    ("street.food.reelss", "IG3_PASSWORD"),
    ("asian.food.hub",     "IG4_PASSWORD"),
    ("viral.food.clips",   "IG5_PASSWORD"),
]
for username, secret_key in ig_configs:
    password = os.environ.get(secret_key, "")
    if password:
        IG_ACCOUNTS.append({"name": username, "username": username, "password": password})
    else:
        print(f"⚠️ {secret_key} not set — skipping {username}")

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

# ── Download from Drive with retry ────────────────────────
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

# ── YouTube upload with retry ──────────────────────────────
def upload_to_youtube(account, title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  📺 Uploading to {account['name']} (attempt {attempt}/{MAX_RETRIES})...")
        try:
            yt = get_youtube_client(account)
            body = {
                "snippet": {
                    "title": title[:100],
                    "description": "🍱 Amazing food content!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Foodie #StreetFood",
                    "categoryId": "22",
                    "tags": ["Shorts", "viral", "food", "japanesefood", "asianfood"],
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
                    print(f"    Progress: {int(status.progress() * 100)}%")
            print(f"  ✅ {account['name']} uploaded!")
            return True
        except Exception as e:
            print(f"  ⚠️ YouTube {account['name']} attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — YouTube upload: {account['name']}")
    return False

# ── Instagram upload with retry ────────────────────────────
def upload_to_instagram(account, title, filename="temp_video.mp4"):
    if not INSTAGRAM_AVAILABLE:
        print(f"  ⚠️ Instagram not available, skipping {account['name']}")
        return False
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  📸 Uploading to {account['name']} (attempt {attempt}/{MAX_RETRIES})...")
        try:
            cl = InstaClient()
            session_file = f"ig_session_{account['username']}.json"
            if os.path.exists(session_file):
                cl.load_settings(session_file)
            cl.login(account["username"], account["password"])
            cl.dump_settings(session_file)
            caption = f"{title}\n\n🍱 Amazing food!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Reels #Trending"
            cl.clip_upload(filename, caption=caption)
            print(f"  ✅ {account['name']} uploaded!")
            return True
        except Exception as e:
            print(f"  ⚠️ Instagram {account['name']} attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Instagram upload: {account['name']}")
    return False

# ── Verify YouTube ─────────────────────────────────────────
def verify_youtube(account, title):
    try:
        yt = get_youtube_client(account)
        resp = yt.search().list(
            part="snippet",
            forMine=True,
            type="video",
            q=title[:50],
            maxResults=5
        ).execute()
        for item in resp.get("items", []):
            if title[:30].lower() in item["snippet"]["title"].lower():
                return True
        return False
    except Exception as e:
        print(f"  ⚠️ YouTube verify failed for {account['name']}: {e}")
        return False

# ── Verify Instagram ───────────────────────────────────────
def verify_instagram(account, title):
    if not INSTAGRAM_AVAILABLE:
        return False
    try:
        cl = InstaClient()
        session_file = f"ig_session_{account['username']}.json"
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(account["username"], account["password"])
        user_id = cl.user_id_from_username(account["username"])
        medias = cl.user_medias(user_id, amount=5)
        for media in medias:
            if media.caption_text and title[:20].lower() in media.caption_text.lower():
                return True
        return False
    except Exception as e:
        print(f"  ⚠️ Instagram verify failed for {account['name']}: {e}")
        return False

# ── Cleanup ────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main ───────────────────────────────────────────────────
def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting to All Accounts")
    print("========================================\n")

    library = load_json(LIBRARY_FILE, [])

    if not library:
        print("⚠️ Drive library is empty. Bot 0 needs to run first.")
        print("========================================\n")
        return

    # Find the latest video uploaded to main channel by Bot 1
    ready = [v for v in library if v.get("used") and v.get("main_channel_video_id") and not v.get("reposted")]

    if not ready:
        print("⚠️ No videos ready to repost. Waiting for Bot 1 to upload first.")
        print("========================================\n")
        return

    video = ready[0]
    title = video["title"]
    print(f"\n▶ Reposting: {title}")

    # Download from Drive
    if not download_from_drive(video["drive_link"], title):
        cleanup()
        return

    yt_results = {}
    ig_results = {}

    # Upload to all YouTube accounts
    print(f"\n  Uploading to {len(YT_ACCOUNTS)} YouTube accounts...")
    for account in YT_ACCOUNTS:
        yt_results[account["name"]] = upload_to_youtube(account, title)
        time.sleep(UPLOAD_DELAY)

    # Upload to all Instagram accounts
    if IG_ACCOUNTS:
        print(f"\n  Uploading to {len(IG_ACCOUNTS)} Instagram accounts...")
        for account in IG_ACCOUNTS:
            ig_results[account["name"]] = upload_to_instagram(account, title)
            time.sleep(UPLOAD_DELAY)
    else:
        print("\n  ⚠️ No Instagram accounts configured")

    cleanup()

    # Mark as reposted
    for v in library:
        if v["video_id"] == video["video_id"]:
            v["reposted"] = True
            break
    save_json(LIBRARY_FILE, library)

    # Wait before verifying
    print("\n  ⏳ Waiting 60s for platforms to process before verifying...")
    time.sleep(60)

    # Verify
    print("\n  🔍 Verifying uploads...")
    yt_verify = {}
    ig_verify = {}

    for account in YT_ACCOUNTS:
        yt_verify[account["name"]] = verify_youtube(account, title) if yt_results.get(account["name"]) else False

    for account in IG_ACCOUNTS:
        ig_verify[account["name"]] = verify_instagram(account, title) if ig_results.get(account["name"]) else False

    # Summary
    print("\n========================================")
    print("📊 UPLOAD SUMMARY")
    print("========================================")
    for name in [a["name"] for a in YT_ACCOUNTS]:
        if yt_verify.get(name):
            print(f"  ✅ YouTube - {name}: Posted & Verified")
        elif yt_results.get(name):
            print(f"  ⚠️ YouTube - {name}: Uploaded but not verified yet")
        else:
            print(f"  ❌ YouTube - {name}: FAILED to upload")

    for name in [a["name"] for a in IG_ACCOUNTS]:
        if ig_verify.get(name):
            print(f"  ✅ Instagram - {name}: Posted & Verified")
        elif ig_results.get(name):
            print(f"  ⚠️ Instagram - {name}: Uploaded but not verified yet")
        else:
            print(f"  ❌ Instagram - {name}: FAILED to upload")

    print("========================================\n")

    print("\n========================================")
    print("BOT 2 DONE!")
    print("========================================\n")

if __name__ == "__main__":
    run_bot2()
