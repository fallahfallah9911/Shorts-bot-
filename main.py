import os, re, time, builtins

_open = builtins.open
def patched_open(file, *args, **kwargs):
    if file == "config.yaml":
        content = _open("config.yaml", "r").read()
        content = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), ""), content)
        _open("config_resolved.yaml", "w").write(content)
        return _open("config_resolved.yaml", *args, **kwargs)
    return _open(file, *args, **kwargs)
builtins.open = patched_open

from bot1 import run_bot1
from bot2 import run_bot2

print("\n🚀 SHORTS BOT SYSTEM STARTING...\n")
try: run_bot1()
except Exception as e: print(f"❌ Bot 1 failed: {e}")
print("⏳ Waiting 60 seconds...")
time.sleep(60)
try: run_bot2()
except Exception as e: print(f"❌ Bot 2 failed: {e}")
print("\n✅ ALL DONE!\n")
