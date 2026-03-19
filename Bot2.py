"""
BOT 2 - REPOST BOT
Takes videos from main channel (or source channels as fallback)
and reposts to all 5 YouTube accounts and 5 Instagram accounts.
"""

import os, json, time, random, yt_dlp, yaml, feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Instagram is optional - skip if not available
try:
    from instagrapi import Client as InstaClient
    INSTAGRAM_AVAILABLE = True
except ImportError:
    INSTAGRAM_AVAILABLE = False
    print("⚠️ instagrapi not available - Instagram uploads disabled")

# ── Config ─────────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
UPLOAD_DELAY    = config.get("upload_delay_seconds", 30)

# ── Credentials from GitHub Secrets ───────────────────────
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

# Instagram accounts - use .get() so missing secrets don't crash the bot
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
UPLOADED_LOG    = "uploaded_bot2.json"
ARCHIVE_LOG     = "archive_bot2.json"
BOT1_ARCHIVE    = "archive_bot1.json"  # Read bot1's archive as fallback

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

# ── Get videos from RSS ────────────────────────────────────
def get_videos_from_rss(channel_id, uploaded_ids):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    print(f"  Fetching RSS: {url}")
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            print(f"  ⚠️ RSS feed empty or unreachable")
            return []
        videos = []
        for e in feed.entries:
            vid = e.get("yt_videoid", "")
            if not vid or vid in uploaded_ids:
                continue
            videos.append({
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": e.get("title", "Untitled")
            })
        print(f"  {len(videos)} new video(s) found")
        return videos
    except Exception as e:
        print(f"  ❌ RSS fetch failed: {e}")
        return []

# ── Download ───────────────────────────────────────────────
def download_video(url, filename="temp_video.mp4"):
    print(f"  Downloading: {url}")
    ydl_opts = {
        "outtmpl": filename,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": False,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Download failed: {filename}")
    print(f"  Downloaded: {os.path.getsize(filename)} bytes")

# ── YouTube upload ─────────────────────────────────────────
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
    print(f"  📺 Uploading to {account['name']}...")
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

# ── Instagram upload ───────────────────────────────────────
def upload_to_instagram(account, title, filename="temp_video.mp4"):
    if not INSTAGRAM_AVAILABLE:
        print(f"  ⚠️ Instagram not available, skipping {account['name']}")
        return
    print(f"  📸 Uploading to {account['name']}...")
    cl = InstaClient()
    session_file = f"ig_session_{account['username']}.json"
    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(account["username"], account["password"])
        cl.dump_settings(session_file)
        caption = f"{title}\n\n🍱 Amazing food!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood #Reels #Trending"
        cl.clip_upload(filename, caption=caption)
        print(f"  ✅ {account['name']} uploaded!")
    except Exception as e:
        print(f"  ❌ {account['name']} Instagram failed: {e}")

# ── Cleanup ────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Process one video to all accounts ─────────────────────
def process_video(video, uploaded_log, archive):
    vid = video["video_id"]
    print(f"\n▶ Processing: {video['title']}")
    print(f"  URL: {video['url']}")

    # Download
    try:
        download_video(video["url"])
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        return False

    success_count = 0

    # Upload to all YouTube accounts
    print(f"\n  Uploading to {len(YT_ACCOUNTS)} YouTube accounts...")
    for account in YT_ACCOUNTS:
        try:
            upload_to_youtube(account, video["title"])
            success_count += 1
        except Exception as e:
            print(f"  ❌ YouTube {account['name']} failed: {e}")
        time.sleep(UPLOAD_DELAY)

    # Upload to Instagram accounts (if configured)
    if IG_ACCOUNTS:
        print(f"\n  Uploading to {len(IG_ACCOUNTS)} Instagram accounts...")
        for account in IG_ACCOUNTS:
            try:
                upload_to_instagram(account, video["title"])
            except Exception as e:
                print(f"  ❌ Instagram {account['name']} failed: {e}")
            time.sleep(UPLOAD_DELAY)
    else:
        print("\n  ⚠️ No Instagram accounts configured (add IG1_PASSWORD - IG5_PASSWORD secrets)")

    # Save state
    uploaded_log[vid] = {"title": video["title"], "url": video["url"]}
    save_json(UPLOADED_LOG, uploaded_log)

    if not any(v["video_id"] == vid for v in archive):
        archive.append(video)
        save_json(ARCHIVE_LOG, archive)

    cleanup()
    print(f"\n  ✅ Done processing: {video['title']}")
    return success_count > 0

# ── Main ───────────────────────────────────────────────────
def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting Videos")
    print("========================================\n")

    uploaded_log = load_json(UPLOADED_LOG, {})
    archive      = load_json(ARCHIVE_LOG, [])
    
    # Also load bot1's archive as additional fallback source
    bot1_archive = load_json(BOT1_ARCHIVE, [])

    video_to_post = None

    # ── Step 1: Check main channel RSS ──────────────────────
    print("🔍 Step 1: Checking main channel RSS...")
    main_videos = get_videos_from_rss(MAIN_CHANNEL["channel_id"], uploaded_log)
    if main_videos:
        video_to_post = main_videos[0]
        print(f"  ✅ Found on main channel: {video_to_post['title']}")

    # ── Step 2: Check source channels ───────────────────────
    if not video_to_post:
        print("\n🔍 Step 2: Checking source channels...")
        for channel in SOURCE_CHANNELS:
            print(f"  Checking {channel['name']}...")
            videos = get_videos_from_rss(channel["id"], uploaded_log)
            if videos:
                video_to_post = videos[0]
                print(f"  ✅ Found in {channel['name']}: {video_to_post['title']}")
                break

    # ── Step 3: Use bot2 archive ─────────────────────────────
    if not video_to_post and archive:
        print("\n📦 Step 3: Using bot2 archive...")
        video_to_post = random.choice(archive)
        print(f"  Using: {video_to_post['title']}")

    # ── Step 4: Use bot1 archive ─────────────────────────────
    if not video_to_post and bot1_archive:
        print("\n📦 Step 4: Using bot1 archive...")
        video_to_post = random.choice(bot1_archive)
        print(f"  Using: {video_to_post['title']}")

    # ── Nothing to post ──────────────────────────────────────
    if not video_to_post:
        print("\n⚠️ No videos found anywhere. Nothing to post today.")
    else:
        process_video(video_to_post, uploaded_log, archive)

    print("\n========================================")
    print("BOT 2 DONE!")
    print("========================================\n")

if __name__ == "__main__":
    run_bot2()
