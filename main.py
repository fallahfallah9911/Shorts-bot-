import time
from bot1 import run_bot1
from bot2 import run_bot2

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")
try:
    run_bot1()
except Exception as e:
    print(f"❌ Bot 1 failed: {e}")
print("⏳ Waiting 60 seconds before Bot 2 starts...")
time.sleep(60)
try:
    run_bot2()
except Exception as e:
    print(f"❌ Bot 2 failed: {e}")
print("\n✅ ALL DONE! Check your accounts.\n")
