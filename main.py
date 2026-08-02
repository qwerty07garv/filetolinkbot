import sys
import os
import traceback

print("========================================", flush=True)
print("🚀 MOVIESHOUSE PRO CLOUD ENGINE BOOTSTRAP", flush=True)
print(f"🐍 Python Version : {sys.version}", flush=True)
print(f"📁 Current Dir    : {os.getcwd()}", flush=True)
print(f"🔌 Port           : {os.getenv('PORT', '10000')}", flush=True)
print("========================================", flush=True)

try:
    # Ensure current directory is on sys.path
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if curr_dir not in sys.path:
        sys.path.insert(0, curr_dir)

    import bot
except Exception as e:
    print("❌ FATAL APPLICATION ENGINE ERROR:", flush=True)
    traceback.print_exc()
    sys.exit(1)
