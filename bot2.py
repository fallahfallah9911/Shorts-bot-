"""
BOT 2 - REPOST BOT
Takes Shorts from main channel (or source channels as fallback)
and reposts to all 5 YouTube accounts and 5 Instagram accounts.
Includes retry logic and end-of-run verification summary.
"""

import os, json, time, random, yt_dlp, yaml, feedparser, isodate
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

SOURCE_CHANNELS = config["source_channels"]
UPLOAD_DELAY    = config.get("upload_delay_seconds", 30)
MAX_RETRIES     = 3
RETRY_WAIT      = 30

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
UPLOADED_LOG = "uploaded_bot2.json"
ARCHIVE_LOG  = "archive_bot2.json"
BOT1_ARCHIVE = "archive_bot1.json"

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

# ── Check if Short ─────────────────────────────────────────
def is_short(video_id, yt_client):
    try:
        resp = yt_client.videos().list(part="contentDetails", id=video_id).execute()
        items = resp.get("items", [])
        if not items:
            return False
        duration = isodate.parse_duration(items[0]["contentDetails"]["duration"]).total_seconds()
        print(f"  Duration: {duration}s")
        return duration <= 60
    except Exception as e:
        print(f"  ⚠️ Duration check failed: {e}")
        return False

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

# ── Download with retry ────────────────────────────────────
def download_video(url, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Downloading (attempt {attempt}/{MAX_RETRIES}): {url}")
        try:
            if os.path.exists(filename):
                os.remove(filename)
            ydl_opts = {
                "outtmpl": filename,
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "quiet": False,
                "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if not os.path.exists(filename):
                raise FileNotFoundError("File not found after download")
            print(f"  Downloaded: {os.path.getsize(filename)} bytes")
            return True
        except Exception as e:
            print(f"  ⚠️ Download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Download: {url}")
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

# ── Process one video ──────────────────────────────────────
def process_video(video, uploaded_log, archive):
    vid   = video["video_id"]
    title = video["title"]
    print(f"\n▶ Processing: {title}")

    if not download_video(video["url"]):
        return False

    yt_results = {}
    ig_results = {}

    print(f"\n  Uploading to {len(YT_ACCOUNTS)} YouTube accounts...")
    for account in YT_ACCOUNTS:
        yt_results[account["name"]] = upload_to_youtube(account, title)
        time.sleep(UPLOAD_DELAY)

    if IG_ACCOUNTS:
        print(f"\n  Uploading to {len(IG_ACCOUNTS)} Instagram accounts...")
        for account in IG_ACCOUNTS:
            ig_results[account["name"]] = upload_to_instagram(account, title)
            time.sleep(UPLOAD_DELAY)
    else:
        print("\n  ⚠️ No Instagram accounts configured")

    uploaded_log[vid] = {"title": title, "url": video["url"]}
    save_json(UPLOADED_LOG, uploaded_log)
    if not any(v["video_id"] == vid for v in archive):
        archive.append(video)
        save_json(ARCHIVE_LOG, archive)

    cleanup()

    print("\n  ⏳ Waiting 60s for platforms to process before verifying...")
    time.sleep(60)

    print("\n  🔍 Verifying uploads...")
    yt_verify = {}
    ig_verify = {}

    for account in YT_ACCOUNTS:
        yt_verify[account["name"]] = verify_youtube(account, title) if yt_results.get(account["name"]) else False

    for account in IG_ACCOUNTS:
        ig_verify[account["name"]] = verify_instagram(account, title) if ig_results.get(account["name"]) else False

    # Print summary
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
    return any(yt_results.values())

# ── Main ───────────────────────────────────────────────────
def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting Shorts")
    print("========================================\n")

    uploaded_log  = load_json(UPLOADED_LOG, {})
    archive       = load_json(ARCHIVE_LOG, [])
    bot1_archive  = load_json(BOT1_ARCHIVE, [])
    yt_client     = get_youtube_client(MAIN_CHANNEL)
    video_to_post = None

    # Step 1: Main channel RSS
    print("🔍 Step 1: Checking main channel RSS...")
    for v in get_videos_from_rss(MAIN_CHANNEL["channel_id"], uploaded_log):
        if is_short(v["video_id"], yt_client):
            video_to_post = v
            print(f"  ✅ Found Short on main channel: {v['title']}")
            break
        print(f"  ⏭️ Not a Short, skipping: {v['title']}")

    # Step 2: Source channels
    if not video_to_post:
        print("\n🔍 Step 2: Checking source channels...")
        for channel in SOURCE_CHANNELS:
            print(f"  Checking {channel['name']}...")
            for v in get_videos_from_rss(channel["id"], uploaded_log):
                if is_short(v["video_id"], yt_client):
                    video_to_post = v
                    print(f"  ✅ Found Short in {channel['name']}: {v['title']}")
                    break
            if video_to_post:
                break

    # Step 3: Bot2 archive
    if not video_to_post and archive:
        print("\n📦 Step 3: Using bot2 archive...")
        video_to_post = random.choice(archive)
        print(f"  Using: {video_to_post['title']}")

    # Step 4: Bot1 archive
    if not video_to_post and bot1_archive:
        print("\n📦 Step 4: Using bot1 archive...")
        video_to_post = random.choice(bot1_archive)
        print(f"  Using: {video_to_post['title']}")

    if not video_to_post:
        print("\n⚠️ No Shorts found anywhere. Nothing to post today.")
    else:
        process_video(video_to_post, uploaded_log, archive)

    print("\n========================================")
    print("BOT 2 DONE!")
    print("========================================\n")

if __name__ == "__main__":
    run_bot2()
