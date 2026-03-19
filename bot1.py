import os, json, time, random, yt_dlp, yaml, feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
SHORTS_PER_DAY  = config["shorts_per_day"]
UPLOAD_DELAY    = config["upload_delay_seconds"]

MAIN_CHANNEL = {
    "channel_id":    "UCqsyePuDbG_GdWgr38CiaBg",
    "client_id":     os.environ["MAIN_CLIENT_ID"],
    "client_secret": os.environ["MAIN_CLIENT_SECRET"],
    "refresh_token": os.environ["MAIN_REFRESH_TOKEN"],
}

UPLOADED_LOG = "uploaded_bot1.json"
ARCHIVE_LOG  = "archive_bot1.json"

def load_json(f): return json.load(open(f)) if os.path.exists(f) else ([] if "bot1" in f else {})
def save_json(f, d): json.dump(d, open(f,"w"), indent=2)

def get_shorts(channel_id, uploaded):
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    shorts = []
    for e in feed.entries:
        vid = e.get("yt_videoid","")
        if not vid or vid in uploaded: continue
        url = f"https://www.youtube.com/shorts/{vid}"
        try:
            with yt_dlp.YoutubeDL({"quiet":True,"skip_download":True}) as ydl:
                info = ydl.extract_info(url, download=False)
                if info.get("duration",999) <= 60:
                    shorts.append({"video_id":vid,"url":url,"title":e.title})
        except: pass
    return shorts

def download(url, f="temp_video.mp4"):
    with yt_dlp.YoutubeDL({"outtmpl":f,"format":"mp4","quiet":True}) as ydl: ydl.download([url])

def get_yt_client(account):
    creds = Credentials(token=None, refresh_token=account["refresh_token"],
        client_id=account["client_id"], client_secret=account["client_secret"],
        token_uri="https://oauth2.googleapis.com/token")
    creds.refresh(Request())
    return build("youtube","v3",credentials=creds)

def upload_main(title, f="temp_video.mp4"):
    yt = get_yt_client(MAIN_CHANNEL)
    body = {"snippet":{"title":title,"description":"🍱 Amazing food!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood","categoryId":"22","tags":["Shorts","viral","food","japanesefood","asianfood"],"defaultLanguage":"en"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}
    req = yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(f,chunksize=-1,resumable=True))
    r = None
    while r is None: _, r = req.next_chunk()
    print(f"  ✅ Uploaded: https://youtube.com/shorts/{r.get('id')}")

def cleanup(f="temp_video.mp4"):
    if os.path.exists(f): os.remove(f)

def run_bot1():
    print("\n========================================")
    print("BOT 1 STARTED — Sourcing Shorts")
    print("========================================\n")
    uploaded = load_json(UPLOADED_LOG)
    archive  = load_json(ARCHIVE_LOG)
    count = 0

    for ch in SOURCE_CHANNELS:
        if count >= SHORTS_PER_DAY: break
        print(f"🔍 Checking: {ch['name']} ({ch['id']})")
        shorts = get_shorts(ch["id"], uploaded)
        if not shorts:
            print("  No new Shorts.\n"); continue
        for s in shorts:
            if count >= SHORTS_PER_DAY: break
            print(f"▶ {s['title']}")
            try:
                download(s["url"])
                upload_main(s["title"])
                uploaded.append(s["video_id"])
                save_json(UPLOADED_LOG, uploaded)
                if not any(v["video_id"]==s["video_id"] for v in archive):
                    archive.append(s); save_json(ARCHIVE_LOG, archive)
                count += 1
                cleanup()
                time.sleep(UPLOAD_DELAY)
            except Exception as e:
                print(f"  ❌ {e}"); cleanup()

    if count == 0:
        print("\n⚠️ No new Shorts! Trying archive...\n")
        if archive:
            s = random.choice(archive)
            try:
                download(s["url"]); upload_main(s["title"]); count += 1; cleanup()
            except Exception as e:
                print(f"  ❌ {e}"); cleanup()
        else:
            print("  ⚠️ Archive empty too.")

    print(f"\n========================================")
    print(f"BOT 1 DONE — Uploaded {count} Short(s)")
    print(f"========================================\n")

if __name__ == "__main__":
    run_bot1()
