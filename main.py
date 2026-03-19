"""
MAIN - Runs Bot 1 then Bot 2
Loads credentials from environment variables (GitHub Secrets)
"""

import os
import time
import yaml

# ── Inject environment variables into config ───────────────
def load_config_with_secrets():
    with open("config.yaml", "r") as f:
        content = f.read()

    # Replace all ${VAR_NAME} with actual environment variable values
    import re
    def replace_env(match):
        var_name = match.group(1)
        value = os.environ.get(var_name, "")
        if not value:
            print(f"⚠️  WARNING: Environment variable '{var_name}' is not set!")
        return value

    content = re.sub(r'\$\{(\w+)\}', replace_env, content)

    with open("config_resolved.yaml", "w") as f:
        f.write(content)

    print("✅ Config loaded with secrets from environment variables")

# ── Patch config path in bots ──────────────────────────────
import builtins
_original_open = builtins.open

def patched_open(file, *args, **kwargs):
    if file == "config.yaml":
        return _original_open("config_resolved.yaml", *args, **kwargs)
    return _original_open(file, *args, **kwargs)

builtins.open = patched_open

# ── Load config with secrets ───────────────────────────────
load_config_with_secrets()

# ── Now import and run bots ────────────────────────────────
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
