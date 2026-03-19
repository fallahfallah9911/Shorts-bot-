"""
MAIN - Entry point
Runs Bot 1 then Bot 2 sequentially.
"""
import time
import traceback

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")

# Run Bot 1
try:
    from bot1 import run_bot1
    run_bot1()
except Exception as e:
    print(f"❌ Bot 1 crashed: {e}")
    traceback.print_exc()

# Wait for YouTube to process the upload
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
