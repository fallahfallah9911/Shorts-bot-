"""
MAIN - Runs Bot 1 then Bot 2
-----------------------------
Bot 1: Source channels → Your main channel
Bot 2: Your main channel → All YT + IG accounts
"""

import time
from bot1 import run_bot1
from bot2 import run_bot2

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")

# Step 1: Bot 1 - find and upload new Shorts to main channel
try:
    run_bot1()
except Exception as e:
    print(f"❌ Bot 1 failed: {e}")

# Wait for YouTube to index the new upload
print("⏳ Waiting 60 seconds before Bot 2 starts...")
time.sleep(60)

# Step 2: Bot 2 - repost from main channel to all accounts
try:
    run_bot2()
except Exception as e:
    print(f"❌ Bot 2 failed: {e}")

print("\n✅ ALL DONE! Check your accounts.\n")
