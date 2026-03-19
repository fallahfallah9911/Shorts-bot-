import os, json, time, random, yt_dlp, yaml, feedparser
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from instagrapi import Client as InstaClient
from instagrapi.exceptions import LoginRequired

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

SOURCE_CHANNELS = config["source_channels"]
UPLOAD_DELAY    = config["upload_delay_seconds"]

MAIN_CHANNEL = {
    "channel_id":    "UCqsyePuDbG_GdWgr38CiaBg",
    "client_id":     os.environ["MAIN_CLIENT_ID"],
    "client_secret": os.environ["MAIN_CLIENT_SECRET"],
    "refresh_token": os.environ["MAIN_REFRESH_TOKEN"],
}

YT_ACCOUNTS = [
    {"name":"Ytfall1","channel_id":"UCvGfvmbe4hLs_56Uq0jNTWg","client_id":os.environ["YT1_CLIENT_ID"],"client_secret":os.environ["YT1_CLIENT_SECRET"],"refresh_token":os.environ["YT1_REFRESH_TOKEN"]},
    {"name":"Ytfall2","channel_id":"UCB8iKg-jfS8Wq3YOwMn001A","client_id":os.environ["YT2_CLIENT_ID"],"client_secret":os.environ["YT2_CLIENT_SECRET"],"refresh_token":os.environ["YT2_REFRESH_TOKEN"]},
    {"name":"Ytfall3","channel_id":"UCqrFyTdlL4bXF4fk-8JNIqQ","client_id":os.environ["YT3_CLIENT_ID"],"client_secret":os.environ["YT3_CLIENT_SECRET"],"refresh_token":os.environ["YT3_REFRESH_TOKEN"]},
    {"name":"Ytfall4","channel_id":"UCQ15QUccIcKi-ecC2OyO7Ow","client_id":os.environ["YT4_CLIENT_ID"],"client_secret":os.environ["YT4_CLIENT_SECRET"],"refresh_token":os.environ["YT4_REFRESH_TOKEN"]},
    {"name":"Ytfall5","channel_id":"UC9nx9_nFwP4ivbGT2GdaC7Q","client_id":os.environ["YT5_CLIENT_ID"],"client_secret":os.environ["YT5_CLIENT_SECRET"],"refresh_token":os.environ["YT5_REFRESH_TOKEN"]},
]

IG_ACCOUNTS = [
    {"name":"japanese_foodhouse","username":"japanese_foodhouse","password":os.environ["IG1_PASSWORD"]},
    {"name":"tokyo.food.daily","username":"tokyo.food.daily","password":os.environ["IG2_PASSWORD"]},
    {"name":"street.food.reelss","username":"street.food.reelss","password":os.environ["IG3_PASSWORD"]},
    {"name":"asian.food.hub","username":"asian.food.hub","password":os.environ["IG4_PASSWORD"]},
    {"name":"viral.food.clips","username":"viral.food.clips","password":os.environ["IG5_PASSWORD"]},
]

UPLOADED_LOG = "uploaded_bot2.json"
ARCHIVE_LOG  = "archive_bot2.json"

def load_json(f, default): return json.load(open(f)) if os.path.exists(f) else default
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

def upload_yt(account, title, f="temp_video.mp4"):
    print(f"  📺 {account['name']}")
    yt = get_yt_client(account)
    body = {"snippet":{"title":title,"description":"🍱 Amazing food!\n\n#Shorts #Food #Viral #JapaneseFood #AsianFood","categoryId":"22","tags":["Shorts","viral","food"],"defaultLanguage":"en"},"status":{"privacyStatus":"public","selfDeclaredMadeForKids":False}}
    req = yt.videos().insert(part="snippet,status",body=body,media_body=MediaFileUpload(f,chunksize=-1,resumable=True))
    r = None
    while r is None: _, r = req.next_chunk()
    print(f"  ✅ Done")

def upload_ig(account, title, f="temp_video.mp4"):
    print(f"  📸 {account['name']}")
    cl = InstaClient()
    sf = f"ig_session_{account['username']}.json"
    try:
        if os.path.exists(sf): cl.load_settings(sf)
        cl.login(account["username"], account["password"])
        cl.dump_settings(sf)
    except Exception as e:
        print(f"  ❌ IG login failed: {e}"); return
    try:
        cl.clip_upload(f, caption=f"{title}\n\n#Shorts #Food #Viral #JapaneseFood #Reels")
        print(f"  ✅ Done")
    except Exception as e:
        print(f"  ❌ IG upload failed: {e}")

def cleanup(f="temp_video.mp4"):
    if os.path.exists(f): os.remove(f)

def process(short, uploaded_log, archive):
    vid = short["video_id"]
    print(f"\n▶ {short['title']}")
    try: download(short["url"])
    except Exception as e: print(f"  ❌ Download failed: {e}"); return

    for acc in YT_ACCOUNTS:
        try: upload_yt(acc, short["title"])
        except Exception as e: print(f"  ❌ {acc['name']}: {e}")
        time.sleep(UPLOAD_DELAY)

    for acc in IG_ACCOUNTS:
        try: upload_ig(acc, short["title"])
        except Exception as e: print(f"  ❌ {acc['name']}: {e}")
        time.sleep(UPLOAD_DELAY)

    uploaded_log[vid] = short["title"]
    save_json(UPLOADED_LOG, uploaded_log)
    if not any(v["video_id"]==vid for v in archive):
        archive.append(short); save_json(ARCHIVE_LOG, archive)
    cleanup()

def run_bot2():
    print("\n========================================")
    print("BOT 2 STARTED — Reposting Shorts")
    print("========================================\n")

    uploaded_log = load_json(UPLOADED_LOG, {})
    archive      = load_json(ARCHIVE_LOG, [])
    short = None

    print("🔍 Checking main channel...")
    mains = get_shorts(MAIN_CHANNEL["channel_id"], uploaded_log)
    if mains:
        print(f"  ✅ Found {len(mains)} on main channel!")
        short = mains[0]
    else:
        print("  Nothing on main. Checking source channels...")
        for ch in SOURCE_CHANNELS:
            print(f"  🔍 {ch['name']}")
            found = get_shorts(ch["id"], uploaded_log)
            if found:
                short = found[0]
                print(f"  ✅ Found: {short['title']}")
                break
        if not short:
            if archive:
                short = random.choice(archive)
                print(f"  📦 Using archive: {short['title']}")
            else:
                print("  ⚠️ Nothing to post.")

    if short:
        process(short, uploaded_log, archive)

    print("\n========================================")
    print("BOT 2 DONE — All accounts updated!")
    print("========================================\n")

if __name__ == "__main__":
    run_bot2()
