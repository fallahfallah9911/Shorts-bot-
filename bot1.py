"""
BOT 1 - SOURCE BOT
Fetches SHORTS ONLY from source channels via RSS + YouTube API duration check.
Uploads to main channel as a Short.
"""

import os, json, time, random, yt_dlp, yaml, feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import isodate

# ── Config ─────────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
SHORTS_PER_DAY  = config.get("shorts_per_day", 1)
UPLOAD_DELAY    = config.get("upload_delay_seconds", 30)

# ── Credentials from GitHub Secrets ───────────────────────
MAIN_CHANNEL = {
    "channel_id":    os.environ.get("MAIN_CHANNEL_ID", "UCqsyePuDbG_GdWgr38CiaBg"),
    "client_id":     os.environ["MAIN_CLIENT_ID"],
    "client_secret": os.environ["MAIN_CLIENT_SECRET"],
    "refresh_token": os.environ["MAIN_REFRESH_TOKEN"],
}

# ── Log files ──────────────────────────────────────────────
UPLOADED_LOG = "uploaded_bot1.json"
ARCHIVE_LOG  = "archive_bot1.json"

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

# ── YouTube API client ─────────────────────────────────────
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

# ── Check if video is a Short (≤ 60 seconds) ──────────────
def is_short(video_id, yt_client):
    try:
        resp = yt_client.videos().list(
            part="contentDetails",
            id=video_id
        ).execute()
        items = resp.get("items", [])
        if not items:
            print(f"  ⚠️ No data found for {video_id}")
            return False
        duration_str = items[0]["contentDetails"]["duration"]
        duration = isodate.parse_duration(duration_str).total_seconds()
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
        print(f"  RSS returned {len(feed.entries)} entries")
        videos = []
        for e in feed.entries:
            vid = e.get("yt_videoid", "")
            if not vid:
                continue
            if vid in uploaded_ids:
                print(f"  Already uploaded: {vid}")
                continue
            videos.append({
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": e.get("title", "Untitled")
            })
        print(f"  {len(videos)} unprocessed video(s) found")
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
        "no_warnings": False,
        "merge_output_format": "mp4",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Download failed - file not found: {filename}")
    size = os.path.getsize(filename)
    print(f"  Downloaded: {size} bytes")

# ── Upload to main channel ─────────────────────────────────
def upload_to_main(title, filename="temp_video.mp4"):
    print(f"  Uploading to main channel: {title}")
    yt = get_youtube_client(MAIN_CHANNEL)
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

# ── Cleanup ────────────────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)
        print(f"  Cleaned up {filename}")

# ── Main ───────────────────────────────────────────────────
def run_bot1():
    print("\n========================================")
    print("BOT 1 STARTED — Sourcing Shorts")
    print("========================================\n")

    uploaded = load_json(UPLOADED_LOG, [])
    archive  = load_json(ARCHIVE_LOG, [])

    if isinstance(uploaded, dict):
        uploaded = list(uploaded.keys())

    # Get YT client for duration checks
    yt_client = get_youtube_client(MAIN_CHANNEL)

    count = 0

    for channel in SOURCE_CHANNELS:
        if count >= SHORTS_PER_DAY:
            break

        print(f"\n🔍 Checking: {channel['name']} ({channel['id']})")
        videos = get_videos_from_rss(channel["id"], uploaded)

        if not videos:
            print(f"  No new videos in {channel['name']}\n")
            continue

        for video in videos:
            if count >= SHORTS_PER_DAY:
                break

            print(f"\n▶ Checking if Short: {video['title']}")

            # Mark as seen regardless so we don't recheck it every run
            if video["video_id"] not in uploaded:
                uploaded.append(video["video_id"])
                save_json(UPLOADED_LOG, uploaded)

            if not is_short(video["video_id"], yt_client):
                print(f"  ⏭️ Not a Short, skipping.")
                continue

            print(f"  ✅ Confirmed Short! Downloading...")
            try:
                download_video(video["url"])
                upload_to_main(video["title"])

                if not any(v["video_id"] == video["video_id"] for v in archive):
                    archive.append(video)
                    save_json(ARCHIVE_LOG, archive)

                count += 1
                cleanup()
                print(f"  Waiting {UPLOAD_DELAY}s before next upload...")
                time.sleep(UPLOAD_DELAY)

            except Exception as e:
                print(f"  ❌ Failed: {e}")
                cleanup()

    # Fallback to archive
    if count == 0:
        print("\n⚠️ No new Shorts found in source channels.")
        if archive:
            video = random.choice(archive)
            print(f"  📦 Falling back to archive: {video['title']}")
            try:
                download_video(video["url"])
                upload_to_main(video["title"])
                count += 1
                cleanup()
            except Exception as e:
                print(f"  ❌ Archive upload failed: {e}")
                cleanup()
        else:
            print("  ⚠️ Archive is also empty. Nothing to post today.")

    print(f"\n========================================")
    print(f"BOT 1 DONE — Uploaded {count} Short(s)")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot1()
