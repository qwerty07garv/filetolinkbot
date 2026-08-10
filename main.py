import sys
import os
import socket
import asyncio
import traceback
from dotenv import load_dotenv

load_dotenv()

os.environ["WEB_CONCURRENCY"] = "1"

print("========================================", flush=True)
print("🚀 MOVIESHOUSE PRO CLOUD ENGINE BOOTSTRAP", flush=True)
print(f"🐍 Python Version : {sys.version}", flush=True)
print(f"📁 Current Dir    : {os.getcwd()}", flush=True)
print(f"🔌 Port           : {os.getenv('PORT', '10000')}", flush=True)
print("========================================", flush=True)

# 🔒 Single Process Lock via Bind Socket (Prevents Render multi-worker duplicate bot replies)
lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    lock_socket.bind(('127.0.0.1', 49152))
except socket.error:
    print("⚠️ Secondary worker process detected inside container. Exiting to enforce single bot instance.", flush=True)
    sys.exit(0)

try:
    curr_dir = os.path.dirname(os.path.abspath(__file__))
    if curr_dir not in sys.path:
        sys.path.insert(0, curr_dir)

    import bot
    print("⚡ Module 'bot' imported cleanly. Launching bot.main()...", flush=True)
    asyncio.run(bot.main())
except Exception as e:
    print("❌ FATAL APPLICATION ENGINE ERROR:", flush=True)
    traceback.print_exc()
    sys.exit(1)
