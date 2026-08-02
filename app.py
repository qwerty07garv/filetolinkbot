import sys
import os
import traceback

print("========================================", flush=True)
print("🚀 STARTING MOVIESHOUSE PRO CLOUD ENGINE", flush=True)
print(f"🐍 Python Version: {sys.version}", flush=True)
print(f"🔌 Target PORT: {os.getenv('PORT', '10000')}", flush=True)
print("========================================", flush=True)

try:
    import bot
except Exception as e:
    print("❌ FATAL ERROR DURING MODULE IMPORT:", flush=True)
    traceback.print_exc()
    sys.exit(1)
