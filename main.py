"""
MAIN - Entry point
Runs Bot 0 (every 2 days), then Bot 1, then Bot 2.
"""
import time
import traceback
from datetime import datetime

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")
print(f"  Run time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")

# Run Bot 0 every 2 days based on day of year
day_of_year = datetime.utcnow().timetuple().tm_yday
run_bot0 = (day_of_year % 2 == 0)

if run_bot0:
    print("📦 Today is a Bot 0 day — refreshing Drive library...\n")
    try:
        from bot0 import run_bot0 as execute_bot0
        execute_bot0()
    except Exception as e:
        print(f"❌ Bot 0 crashed: {e}")
        traceback.print_exc()
    print("\n⏳ Waiting 60s after Bot 0 before running Bot 1...")
    time.sleep(60)
else:
    print("📦 Not a Bot 0 day — skipping Drive refresh.\n")

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
