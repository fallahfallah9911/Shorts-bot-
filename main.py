"""
MAIN - Entry point
Runs Bot 1 (upload to main channel), then Bot 2 (repost to all accounts).
Videos are manually added to drive_library.json.
"""
import time
import traceback
from datetime import datetime

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")
print(f"  Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

# Run Bot 1
try:
    from bot1 import run_bot1
    run_bot1()
except Exception as e:
    print(f"❌ Bot 1 crashed: {e}")
    traceback.print_exc()

# Wait for YouTube to process
print("\n⏳ Waiting 3 minutes for YouTube to process upload...")
time.sleep(180)

# Run Bot 2
try:
    from bot2 import run_bot2
    run_bot2()
except Exception as e:
    print(f"❌ Bot 2 crashed: {e}")
    traceback.print_exc()

print("\n✅ ALL DONE! Check your accounts.\n")
