"""
BOT 0 - DRIVE MANAGER
Checks source channels for real YouTube Shorts.
Downloads each at highest available quality.
Uploads to Google Drive until storage is full or no Shorts left.
Deletes used videos from Drive to save space.
Runs every 2 days.
"""

import os, json, time, requests, yt_dlp, yaml
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# ── Config ─────────────────────────────────────────────────
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
MAX_RETRIES     = 3
RETRY_WAIT      = 30
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
DRIVE_MAX_BYTES = 14 * 1024 * 1024 * 1024  # 14GB safety limit

# ── Credentials ────────────────────────────────────────────
MAIN_CHANNEL = {
    "channel_id":    os.environ.get("MAIN_CHANNEL_ID", "UCqsyePuDbG_GdWgr38CiaBg"),
    "client_id":     os.environ["MAIN_CLIENT_ID"],
    "client_secret": os.environ["MAIN_CLIENT_SECRET"],
    "refresh_token": os.environ["MAIN_REFRESH_TOKEN"],
}

# ── Log files ──────────────────────────────────────────────
LIBRARY_FILE = "drive_library.json"
SEEN_FILE    = "seen_bot0.json"

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

# ── Google Drive client ────────────────────────────────────
def get_drive_client():
    creds = Credentials(
        token=None,
        refresh_token=MAIN_CHANNEL["refresh_token"],
        client_id=MAIN_CHANNEL["client_id"],
        client_secret=MAIN_CHANNEL["client_secret"],
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(Request())
    return build("drive", "v3", credentials=creds)

# ── Check if video is a real YouTube Short ─────────────────
def is_youtube_short(video_id):
    try:
        url = f"https://www.youtube.com/shorts/{video_id}"
        resp = requests.head(url, allow_redirects=True, timeout=10)
        is_short = "/shorts/" in resp.url
        print(f"  Short check: {resp.url} → {'✅ Short' if is_short else '⏭️ Not a Short'}")
        return is_short
    except Exception as e:
        print(f"  ⚠️ Short check failed: {e}")
        return False

# ── Get Drive storage used ─────────────────────────────────
def get_drive_storage_used():
    try:
        drive = get_drive_client()
        resp = drive.about().get(fields="storageQuota").execute()
        used = int(resp["storageQuota"]["usage"])
        total = int(resp["storageQuota"]["limit"])
        print(f"  Drive storage: {used / 1024**3:.2f}GB / {total / 1024**3:.2f}GB used")
        return used
    except Exception as e:
        print(f"  ⚠️ Could not check Drive storage: {e}")
        return 0

# ── Get all videos from channel via API ───────────────────
def get_all_videos_from_channel(channel_id, seen_ids, yt_client):
    print(f"  Fetching all videos from: {channel_id}")
    videos = []
    next_page_token = None

    while True:
        try:
            params = {
                "part": "snippet",
                "channelId": channel_id,
                "order": "date",
                "type": "video",
                "maxResults": 50
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            resp = yt_client.search().list(**params).execute()

            for item in resp.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in seen_ids:
                    videos.append({
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": item["snippet"]["title"]
                    })

            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

            time.sleep(1)

        except Exception as e:
            print(f"  ❌ API fetch failed: {e}")
            break

    print(f"  Found {len(videos)} unseen video(s)")
    return videos

# ── Download at highest quality ────────────────────────────
def download_video(video_id, filename="temp_video.mp4"):
    url = f"https://www.youtube.com/shorts/{video_id}"
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Downloading (attempt {attempt}/{MAX_RETRIES}): {url}")
        try:
            if os.path.exists(filename):
                os.remove(filename)
            ydl_opts = {
                "outtmpl": filename,
                "format": "best[ext=mp4]/best",
                "quiet": False,
                "merge_output_format": "mp4",
                "extractor_args": {"youtube": {"player_client": ["android"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if not os.path.exists(filename):
                raise FileNotFoundError("File not found after download")
            size = os.path.getsize(filename)
            print(f"  Downloaded: {size / 1024**2:.1f}MB")
            return True, size
        except Exception as e:
            print(f"  ⚠️ Download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Download: {url}")
    return False, 0

# ── Upload to Google Drive ─────────────────────────────────
def upload_to_drive(title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Uploading to Drive (attempt {attempt}/{MAX_RETRIES}): {title}")
        try:
            drive = get_drive_client()
            file_metadata = {
                "name": f"{title[:80]}.mp4",
                "parents": [DRIVE_FOLDER_ID]
            }
            media = MediaFileUpload(filename, mimetype="video/mp4", resumable=True)
            file = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webContentLink"
            ).execute()
            drive_id   = file.get("id")
            drive_link = file.get("webContentLink")
            drive.permissions().create(
                fileId=drive_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()
            print(f"  ✅ Uploaded to Drive: {drive_id}")
            return drive_id, drive_link
        except Exception as e:
            print(f"  ⚠️ Drive upload attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Drive upload: {title}")
    return None, None

# ── Delete used videos from Drive ─────────────────────────
def cleanup_used_from_drive(library):
    drive = get_drive_client()
    removed = []
    for video in library:
        if video.get("reposted") and video.get("drive_id"):
            try:
                drive.files().delete(fileId=video["drive_id"]).execute()
                print(f"  🗑️ Deleted from Drive: {video['title']}")
                removed.append(video["video_id"])
            except Exception as e:
                print(f"  ⚠️ Could not delete {video['title']}: {e}")
    return [v for v in library if v["video_id"] not in removed]

# ── Cleanup local file ─────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main ───────────────────────────────────────────────────
def run_bot0():
    print("\n========================================")
    print("BOT 0 STARTED — Drive Manager")
    print("========================================\n")

    library  = load_json(LIBRARY_FILE, [])
    seen_ids = load_json(SEEN_FILE, [])

    if isinstance(seen_ids, dict):
        seen_ids = list(seen_ids.keys())

    yt_client = get_youtube_client()

    print("🗑️ Step 1: Cleaning reposted videos from Drive...")
    library = cleanup_used_from_drive(library)
    save_json(LIBRARY_FILE, library)
    print(f"  Library now has {len(library)} video(s)\n")

    print("💾 Step 2: Checking Drive storage...")
    storage_used = get_drive_storage_used()
    if storage_used >= DRIVE_MAX_BYTES:
        print("  ⚠️ Drive is full. Skipping download.")
        print("========================================\n")
        return
    print()

    new_count = 0
    print("🔍 Step 3: Fetching Shorts from all source channels...")

    for channel in SOURCE_CHANNELS:
        print(f"\n  📺 Channel: {channel['name']} ({channel['id']})")
        videos = get_all_videos_from_channel(channel["id"], seen_ids, yt_client)

        for video in videos:
            storage_used = get_drive_storage_used()
            if storage_used >= DRIVE_MAX_BYTES:
                print("\n  💾 Drive full. Stopping.")
                break

            print(f"\n  ▶ Checking: {video['title']}")

            seen_ids.append(video["video_id"])
            save_json(SEEN_FILE, seen_ids)

            if not is_youtube_short(video["video_id"]):
                continue

            success, file_size = download_video(video["video_id"])
            if not success:
                cleanup()
                continue

            drive_id, drive_link = upload_to_drive(video["title"])
            cleanup()

            if drive_id:
                library.append({
                    "video_id":   video["video_id"],
                    "title":      video["title"],
                    "url":        video["url"],
                    "drive_id":   drive_id,
                    "drive_link": drive_link,
                    "used":       False,
                    "reposted":   False
                })
                save_json(LIBRARY_FILE, library)
                new_count += 1
                print(f"  ✅ Added to library: {video['title']}")

        else:
            continue
        break

    print(f"\n========================================")
    print(f"BOT 0 DONE — Added {new_count} new Short(s) to Drive")
    print(f"Library total: {len(library)} video(s) ready")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot0()                "order": "date",
                "type": "video",
                "maxResults": 50
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            resp = yt_client.search().list(**params).execute()

            for item in resp.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in seen_ids:
                    videos.append({
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": item["snippet"]["title"]
                    })

            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

            time.sleep(1)

        except Exception as e:
            print(f"  ❌ API fetch failed: {e}")
            break

    print(f"  Found {len(videos)} unseen video(s)")
    return videos

# ── Download at highest quality ────────────────────────────
def download_video(video_id, filename="temp_video.mp4"):
    url = f"https://www.youtube.com/shorts/{video_id}"
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Downloading (attempt {attempt}/{MAX_RETRIES}): {url}")
        try:
            if os.path.exists(filename):
                os.remove(filename)
            ydl_opts = {
                "outtmpl": filename,
                "format": "best[ext=mp4]/best",
                "quiet": False,
                "merge_output_format": "mp4",
                "extractor_args": {"youtube": {"player_client": ["android"]}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            if not os.path.exists(filename):
                raise FileNotFoundError("File not found after download")
            size = os.path.getsize(filename)
            print(f"  Downloaded: {size / 1024**2:.1f}MB")
            return True, size
        except Exception as e:
            print(f"  ⚠️ Download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Download: {url}")
    return False, 0

# ── Upload to Google Drive ─────────────────────────────────
def upload_to_drive(title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Uploading to Drive (attempt {attempt}/{MAX_RETRIES}): {title}")
        try:
            drive = get_drive_client()
            file_metadata = {
                "name": f"{title[:80]}.mp4",
                "parents": [DRIVE_FOLDER_ID]
            }
            media = MediaFileUpload(filename, mimetype="video/mp4", resumable=True)
            file = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webContentLink"
            ).execute()
            drive_id   = file.get("id")
            drive_link = file.get("webContentLink")
            drive.permissions().create(
                fileId=drive_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()
            print(f"  ✅ Uploaded to Drive: {drive_id}")
            return drive_id, drive_link
        except Exception as e:
            print(f"  ⚠️ Drive upload attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Drive upload: {title}")
    return None, None

# ── Delete used videos from Drive ─────────────────────────
def cleanup_used_from_drive(library):
    drive = get_drive_client()
    removed = []
    for video in library:
        if video.get("reposted") and video.get("drive_id"):
            try:
                drive.files().delete(fileId=video["drive_id"]).execute()
                print(f"  🗑️ Deleted from Drive: {video['title']}")
                removed.append(video["video_id"])
            except Exception as e:
                print(f"  ⚠️ Could not delete {video['title']}: {e}")
    return [v for v in library if v["video_id"] not in removed]

# ── Cleanup local file ─────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main ───────────────────────────────────────────────────
def run_bot0():
    print("\n========================================")
    print("BOT 0 STARTED — Drive Manager")
    print("========================================\n")

    library  = load_json(LIBRARY_FILE, [])
    seen_ids = load_json(SEEN_FILE, [])

    if isinstance(seen_ids, dict):
        seen_ids = list(seen_ids.keys())

    yt_client = get_youtube_client()

    print("🗑️ Step 1: Cleaning reposted videos from Drive...")
    library = cleanup_used_from_drive(library)
    save_json(LIBRARY_FILE, library)
    print(f"  Library now has {len(library)} video(s)\n")

    print("💾 Step 2: Checking Drive storage...")
    storage_used = get_drive_storage_used()
    if storage_used >= DRIVE_MAX_BYTES:
        print("  ⚠️ Drive is full. Skipping download.")
        print("========================================\n")
        return
    print()

    new_count = 0
    print("🔍 Step 3: Fetching Shorts from all source channels...")

    for channel in SOURCE_CHANNELS:
        print(f"\n  📺 Channel: {channel['name']} ({channel['id']})")
        videos = get_all_videos_from_channel(channel["id"], seen_ids, yt_client)

        for video in videos:
            storage_used = get_drive_storage_used()
            if storage_used >= DRIVE_MAX_BYTES:
                print("\n  💾 Drive full. Stopping.")
                break

            print(f"\n  ▶ Checking: {video['title']}")

            seen_ids.append(video["video_id"])
            save_json(SEEN_FILE, seen_ids)

            if not is_youtube_short(video["video_id"]):
                continue

            success, file_size = download_video(video["video_id"])
            if not success:
                cleanup()
                continue

            drive_id, drive_link = upload_to_drive(video["title"])
            cleanup()

            if drive_id:
                library.append({
                    "video_id":   video["video_id"],
                    "title":      video["title"],
                    "url":        video["url"],
                    "drive_id":   drive_id,
                    "drive_link": drive_link,
                    "used":       False,
                    "reposted":   False
                })
                save_json(LIBRARY_FILE, library)
                new_count += 1
                print(f"  ✅ Added to library: {video['title']}")

        else:
            continue
        break

    print(f"\n========================================")
    print(f"BOT 0 DONE — Added {new_count} new Short(s) to Drive")
    print(f"Library total: {len(library)} video(s) ready")
    print(f"========================================\n")

if __name__ == "__main__":def get_all_videos_from_channel(channel_id, seen_ids, yt_client):
    print(f"  Fetching all videos from: {channel_id}")
    videos = []
    next_page_token = None

    while True:
        try:
            params = {
                "part": "snippet",
                "channelId": channel_id,
                "order": "date",
                "type": "video",
                "maxResults": 50
            }
            if next_page_token:
                params["pageToken"] = next_page_token

            resp = yt_client.search().list(**params).execute()

            for item in resp.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in seen_ids:
                    videos.append({
                        "video_id": vid,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "title": item["snippet"]["title"]
                    })

            next_page_token = resp.get("nextPageToken")
            if not next_page_token:
                break

            time.sleep(1)  # Small delay between pages

        except Exception as e:
            print(f"  ❌ API fetch failed: {e}")
            break

    print(f"  Found {len(videos)} unseen video(s)")
    return videos

# ── Download at highest quality ────────────────────────────
def download_video(video_id, filename="temp_video.mp4"):
    url = f"https://www.youtube.com/shorts/{video_id}"
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
            size = os.path.getsize(filename)
            print(f"  Downloaded: {size / 1024**2:.1f}MB")
            return True, size
        except Exception as e:
            print(f"  ⚠️ Download attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Download: {url}")
    return False, 0

# ── Upload to Google Drive ─────────────────────────────────
def upload_to_drive(title, filename="temp_video.mp4"):
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"  Uploading to Drive (attempt {attempt}/{MAX_RETRIES}): {title}")
        try:
            drive = get_drive_client()
            file_metadata = {
                "name": f"{title[:80]}.mp4",
                "parents": [DRIVE_FOLDER_ID]
            }
            media = MediaFileUpload(filename, mimetype="video/mp4", resumable=True)
            file = drive.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webContentLink"
            ).execute()
            drive_id   = file.get("id")
            drive_link = file.get("webContentLink")
            # Make publicly readable
            drive.permissions().create(
                fileId=drive_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()
            print(f"  ✅ Uploaded to Drive: {drive_id}")
            return drive_id, drive_link
        except Exception as e:
            print(f"  ⚠️ Drive upload attempt {attempt} failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_WAIT}s...")
                time.sleep(RETRY_WAIT)
    print(f"  ❌ FAILED after {MAX_RETRIES} attempts — Drive upload: {title}")
    return None, None

# ── Delete used videos from Drive ─────────────────────────
def cleanup_used_from_drive(library):
    drive = get_drive_client()
    removed = []
    for video in library:
        if video.get("reposted") and video.get("drive_id"):
            try:
                drive.files().delete(fileId=video["drive_id"]).execute()
                print(f"  🗑️ Deleted from Drive: {video['title']}")
                removed.append(video["video_id"])
            except Exception as e:
                print(f"  ⚠️ Could not delete {video['title']}: {e}")
    return [v for v in library if v["video_id"] not in removed]

# ── Cleanup local file ─────────────────────────────────────
def cleanup(filename="temp_video.mp4"):
    if os.path.exists(filename):
        os.remove(filename)

# ── Main ───────────────────────────────────────────────────
def run_bot0():
    print("\n========================================")
    print("BOT 0 STARTED — Drive Manager")
    print("========================================\n")

    library  = load_json(LIBRARY_FILE, [])
    seen_ids = load_json(SEEN_FILE, [])

    if isinstance(seen_ids, dict):
        seen_ids = list(seen_ids.keys())

    yt_client = get_youtube_client()

    # Step 1: Clean up reposted videos from Drive
    print("🗑️ Step 1: Cleaning reposted videos from Drive...")
    library = cleanup_used_from_drive(library)
    save_json(LIBRARY_FILE, library)
    print(f"  Library now has {len(library)} video(s)\n")

    # Step 2: Check Drive storage
    print("💾 Step 2: Checking Drive storage...")
    storage_used = get_drive_storage_used()
    if storage_used >= DRIVE_MAX_BYTES:
        print("  ⚠️ Drive is full. Skipping download.")
        print("========================================\n")
        return
    print()

    # Step 3: Fetch and download all Shorts
    new_count = 0
    print("🔍 Step 3: Fetching Shorts from all source channels...")

    for channel in SOURCE_CHANNELS:
        print(f"\n  📺 Channel: {channel['name']} ({channel['id']})")
        videos = get_all_videos_from_channel(channel["id"], seen_ids, yt_client)

        for video in videos:
            # Check Drive storage before each download
            storage_used = get_drive_storage_used()
            if storage_used >= DRIVE_MAX_BYTES:
                print("\n  💾 Drive full. Stopping.")
                break

            print(f"\n  ▶ Checking: {video['title']}")

            # Mark as seen immediately
            seen_ids.append(video["video_id"])
            save_json(SEEN_FILE, seen_ids)

            # Check if real Short
            if not is_youtube_short(video["video_id"]):
                continue

            # Download at highest quality
            success, file_size = download_video(video["video_id"])
            if not success:
                cleanup()
                continue

            # Upload to Drive
            drive_id, drive_link = upload_to_drive(video["title"])
            cleanup()

            if drive_id:
                library.append({
                    "video_id":   video["video_id"],
                    "title":      video["title"],
                    "url":        video["url"],
                    "drive_id":   drive_id,
                    "drive_link": drive_link,
                    "used":       False,
                    "reposted":   False
                })
                save_json(LIBRARY_FILE, library)
                new_count += 1
                print(f"  ✅ Added to library: {video['title']}")

        else:
            continue
        break  # Drive full — stop all channels

    print(f"\n========================================")
    print(f"BOT 0 DONE — Added {new_count} new Short(s) to Drive")
    print(f"Library total: {len(library)} video(s) ready")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot0()
