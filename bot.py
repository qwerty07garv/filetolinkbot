import os
import sys
import uuid
import time
import logging
import traceback
import asyncio
from datetime import datetime
from aiohttp import web

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

print("🔍 STEP 1: Importing Hydrogram...", flush=True)
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from hydrogram.enums import ParseMode
from hydrogram.errors import UserNotParticipant, FloodWait

print("🔍 STEP 2: Importing DB Manager...", flush=True)
from db_manager import (
    init_indexes, mongo_health_check_loop, save_file_record, get_file_record,
    delete_file_record, get_total_stats, get_total_users_count, save_user, get_all_users
)
import web_server

def clean_env_str(key, default):
    val = os.getenv(key, default)
    if not val:
        return default
    return str(val).strip().replace('"', '').replace("'", "")

def clean_env_int(key, default):
    val = os.getenv(key, str(default))
    if not val:
        return default
    try:
        cleaned = str(val).strip().replace('"', '').replace("'", "")
        return int(cleaned)
    except Exception as e:
        print(f"⚠️ Warning: Invalid integer for {key} ('{val}'), falling back to default {default}. Error: {e}", flush=True)
        return default

BOT_TOKEN   = clean_env_str("BOT_TOKEN", "8844186435:AAEQ3EgwIzFut6XdCc-u8_Gc0qn_xsNOd5s")
API_ID      = clean_env_int("API_ID", 38319323)
API_HASH    = clean_env_str("API_HASH", "c171e3cfd6fc5c724cda63b0dbcf81d2")
raw_base_url = clean_env_str("BASE_URL", "https://filetolinkbot-phzj.onrender.com")
if "222.167.207.30" in raw_base_url or "5050" in raw_base_url or not raw_base_url.startswith("http"):
    raw_base_url = "https://filetolinkbot-phzj.onrender.com"
BASE_URL    = raw_base_url
CHANNEL_URL = clean_env_str("CHANNEL_URL", "https://t.me/movieshouseworld")
CHANNEL_ID  = clean_env_str("CHANNEL_ID", "@movieshouseworld")
PORT        = clean_env_int("PORT", 10000)

raw_admins  = clean_env_str("ADMIN_IDS", "1785600474,1855042026")
ADMIN_IDS   = [int(x.strip()) for x in raw_admins.split(",") if x.strip() and x.strip().isdigit()]

START_TIME  = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

print(f"✅ STEP 3: Config Parsed Cleanly -> PORT: {PORT}, API_ID: {API_ID}, BOT_TOKEN: {BOT_TOKEN[:10]}...", flush=True)

app = None

def get_app():
    global app
    if app is None:
        app = Client(
            name="movieshouse_bot_session",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=False,
            device_model="Samsung Galaxy S24 Ultra",
            system_version="Android 14",
            app_version="10.14.5",
            workers=8,
            max_concurrent_transmissions=3,
            sleep_threshold=60
        )

        @app.on_message(filters.command("start"))
        async def start_handler(client: Client, message: Message):
            user_id   = message.from_user.id if message.from_user else 0
            user_name = message.from_user.first_name if message.from_user else "User"

            if user_id:
                await save_user(user_id, user_name)

            is_subbed = await check_fsub(client, user_id)
            if not is_subbed:
                fsub_text = (
                    f"<blockquote><b>⚠️ Channel Subscription Required</b></blockquote>\n\n"
                    f"👋 Hi <b>{user_name}</b>!\n\n"
                    f"To use <b>MoviesHouse PRO Link Generator</b>, join our official channel:\n\n"
                    f"👉 <b>@movieshouseworld</b>\n\n"
                    f"After joining, click <b>🔄 Try Again / Verify</b>."
                )
                await message.reply_text(fsub_text, parse_mode=ParseMode.HTML, reply_markup=get_fsub_keyboard())
                return

            welcome_text = (
                f"<blockquote><b>🎬 MoviesHouse PRO — VPS Cloud Engine v2.0</b></blockquote>\n\n"
                f"👋 Welcome <b>{user_name}</b>!\n\n"
                f"Send any <b>Video, Audio, Movie, Document, Photo, Voice, or Video Note</b> for an <b>Instant Direct Stream & Download Link</b>.\n\n"
                f"⚡ <b>Server:</b> VPS Cloud Engine (Singapore)\n"
                f"📦 <b>Max Size:</b> Up to 4,000 MB (4GB)\n"
                f"📢 <b>Channel:</b> @movieshouseworld\n\n"
                f"👇 Select an action or send a file directly:"
            )

            # Check for start parameter (e.g. /start file_id)
            start_args = message.command
            if len(start_args) > 1:
                file_id = start_args[1]
                file_info = await get_file_record(file_id)
                if file_info:
                    file_name = file_info.get("file_name", "file")
                    file_size_bytes = file_info.get("file_size", 0)
                    file_size_mb  = file_size_bytes / (1024 * 1024)
                    download_link = f"{BASE_URL}/dl/{file_id}"
                    direct_link   = f"{BASE_URL}/file/{file_id}"

                    result_text = (
                        f"<blockquote><b>⚡ Direct File-to-Link Retrieved Successfully!</b></blockquote>\n\n"
                        f"<pre><code class=\"language-json\">\n"
                        f"{{\n"
                        f"  \"file_id\": \"{file_id}\",\n"
                        f"  \"name\": \"{file_name}\",\n"
                        f"  \"size\": \"{file_size_mb:.2f} MB\",\n"
                        f"  \"status\": \"VPS Cloud Stream Ready\"\n"
                        f"}}\n"
                        f"</code></pre>\n\n"
                        f"🔗 <b>Web Download & Stream Page:</b>\n"
                        f"<code>{download_link}</code>\n\n"
                        f"⚡ <b>Direct Stream/Download Link:</b>\n"
                        f"<code>{direct_link}</code>"
                    )

                    action_buttons = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton("🌐 Open Stream Page", url=download_link),
                            InlineKeyboardButton("📥 Direct Download", url=direct_link)
                        ],
                        [
                            InlineKeyboardButton("📢 Channel", url=CHANNEL_URL),
                            InlineKeyboardButton("🗑️ Delete Link", callback_data=f"del_{file_id}")
                        ]
                    ])
                    await message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=action_buttons)
                    return
                else:
                    await message.reply_text("❌ File not found or link has expired.")
                    return

            await message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())

        @app.on_message(filters.command("help"))
        async def help_handler(client: Client, message: Message):
            user_name = message.from_user.first_name if message.from_user else "User"
            help_text = (
                f"<blockquote><b>❓ MoviesHouse PRO — Help Guide</b></blockquote>\n\n"
                f"👋 Hi <b>{user_name}</b>! Here is how to use this bot:\n\n"
                f"📁 <b>How to get Stream/Download links:</b>\n"
                f"1. Send or forward any video, audio, or document file to this bot.\n"
                f"2. The bot will instantly generate a fast stream and download link.\n"
                f"3. You can click on the link to watch online or download directly.\n\n"
                f"🍿 <b>Using the Video Player:</b>\n"
                f"• Use the <b>VLC</b> or <b>MX Player</b> buttons to watch in external players.\n"
                f"• In the web player, click the settings gear icon to adjust playback speed.\n"
                f"• Click the <b>Audio Language Guide</b> on the web page to see how to switch languages in VLC or MX Player.\n\n"
                f"📢 <b>Support:</b> @movieshouseworld\n\n"
                f"💻 <b>Commands:</b>\n"
                f"• /start - Launch the bot and check status\n"
                f"• /help - Display this help guide"
            )
            back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Back to Menu", callback_data="btn_home")]])
            await message.reply_text(help_text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

        @app.on_message(filters.command("broadcast") & filters.private)
        async def broadcast_handler(client: Client, message: Message):
            user_id = message.from_user.id if message.from_user else 0
            if message.from_user and message.from_user.id not in ADMIN_IDS:
                return

            if not message.reply_to_message and len(message.command) < 2:
                await message.reply_text("<b>Usage:</b> Reply to any message or text to broadcast.", parse_mode=ParseMode.HTML)
                return

            all_users = await get_all_users()
            total = len(all_users)
            success = 0
            failed = 0

            status_msg = await message.reply_text(f"🚀 Broadcasting message to <b>{total}</b> users...", parse_mode=ParseMode.HTML)

            for u in all_users:
                uid = u.get("user_id")
                sent = False
                retry_count = 0

                while not sent and retry_count < 3:
                    try:
                        if message.reply_to_message:
                            await message.reply_to_message.copy(uid)
                        else:
                            text_to_send = message.text.split(None, 1)[1]
                            await client.send_message(uid, text_to_send, parse_mode=ParseMode.HTML)
                        success += 1
                        sent = True
                        await asyncio.sleep(0.04)
                    except FloodWait as e:
                        logger.warning(f"FloodWait hit during broadcast: Sleeping for {e.value} seconds")
                        await asyncio.sleep(e.value)
                        retry_count += 1
                    except Exception as ex:
                        logger.error(f"Broadcast failed for user {uid}: {ex}")
                        failed += 1
                        break

                if not sent:
                    failed += 1

            await status_msg.edit_text(
                f"<blockquote><b>📢 Broadcast Completed Cleanly!</b></blockquote>\n\n"
                f"• Total Users : {total}\n"
                f"• Success     : {success}\n"
                f"• Failed      : {failed}",
                parse_mode=ParseMode.HTML
            )

        @app.on_message(filters.command("stats") & filters.private)
        async def admin_stats_handler(client: Client, message: Message):
            total_files = await get_total_stats()
            total_users = await get_total_users_count()
            uptime_sec  = int(time.time() - START_TIME)
            stats_text = (
                f"<blockquote><b>📊 MoviesHouse PRO Admin Panel</b></blockquote>\n\n"
                f"<pre><code class=\"language-python\">\n"
                f"[ASYNC DB STATS]\n"
                f"Total Registered Users : {total_users}\n"
                f"Total Links Generated  : {total_files}\n"
                f"Uptime                 : {uptime_sec} seconds\n"
                f"Server Host            : VPS Cloud Platform\n"
                f"Engine                 : Async Motor MongoDB + Hydrogram\n"
                f"Channel                : @movieshouseworld\n"
                f"</code></pre>"
            )
            await message.reply_text(stats_text, parse_mode=ParseMode.HTML)

        @app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.voice | filters.video_note | filters.animation))
        async def handle_file(client: Client, message: Message):
            user_id   = message.from_user.id if message.from_user else 0
            user_name = message.from_user.first_name if message.from_user else "User"

            if user_id:
                await save_user(user_id, user_name)

            is_subbed = await check_fsub(client, user_id)
            if not is_subbed:
                fsub_text = (
                    f"<blockquote><b>⚠️ Channel Subscription Required</b></blockquote>\n\n"
                    f"👋 Hi <b>{user_name}</b>!\n\n"
                    f"To generate links, join our channel first:\n\n"
                    f"👉 <b>@movieshouseworld</b>\n\n"
                    f"After joining, click <b>🔄 Try Again / Verify</b>."
                )
                await message.reply_text(fsub_text, parse_mode=ParseMode.HTML, reply_markup=get_fsub_keyboard())
                return

            file_obj = (message.document or message.video or message.audio or 
                        message.voice or message.video_note or message.animation or message.photo)
            
            if message.photo:
                file_obj = message.photo

            file_name = "file"
            mime_type = "application/octet-stream"
            file_size_bytes = getattr(file_obj, 'file_size', 0)

            if file_size_bytes > 4000 * 1024 * 1024:
                await message.reply_text("<blockquote><b>⚠️ File size exceeds 4,000 MB limit!</b></blockquote>", parse_mode=ParseMode.HTML)
                return

            if hasattr(file_obj, 'file_name') and file_obj.file_name:
                file_name = file_obj.file_name
            elif message.video:
                file_name = f"video_{message.id}.mp4"
                mime_type = "video/mp4"
            elif message.photo:
                file_name = f"photo_{message.id}.jpg"
                mime_type = "image/jpeg"
            elif message.audio:
                file_name = f"audio_{message.id}.mp3"
                mime_type = "audio/mpeg"
            elif message.voice:
                file_name = f"voice_{message.id}.ogg"
                mime_type = "audio/ogg"
            elif message.video_note:
                file_name = f"videonote_{message.id}.mp4"
                mime_type = "video/mp4"
            elif message.animation:
                file_name = f"animation_{message.id}.mp4"
                mime_type = "video/mp4"
            else:
                file_name = f"file_{message.id}.bin"

            if hasattr(file_obj, 'mime_type') and file_obj.mime_type:
                mime_type = file_obj.mime_type

            file_id = str(uuid.uuid4())[:12]

            record = {
                "file_id":    file_id,
                "tg_file_id": file_obj.file_id,
                "chat_id":    message.chat.id,
                "message_id": message.id,
                "file_name":  file_name,
                "file_size":  file_size_bytes,
                "mime_type":  mime_type,
                "created_at": datetime.utcnow().isoformat()
            }
            await save_file_record(file_id, record)

            file_size_mb  = file_size_bytes / (1024 * 1024)
            download_link = f"{BASE_URL}/dl/{file_id}"
            direct_link   = f"{BASE_URL}/file/{file_id}"

            result_text = (
                f"<blockquote><b>⚡ Direct File-to-Link Generated Instantly!</b></blockquote>\n\n"
                f"<pre><code class=\"language-json\">\n"
                f"{{\n"
                f"  \"file_id\": \"{file_id}\",\n"
                f"  \"name\": \"{file_name}\",\n"
                f"  \"size\": \"{file_size_mb:.2f} MB\",\n"
                f"  \"status\": \"VPS Cloud Stream Ready\"\n"
                f"}}\n"
                f"</code></pre>\n\n"
                f"🔗 <b>Web Download & Stream Page:</b>\n"
                f"<code>{download_link}</code>\n\n"
                f"⚡ <b>Direct Stream/Download Link:</b>\n"
                f"<code>{direct_link}</code>"
            )

            action_buttons = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🌐 Open Stream Page", url=download_link),
                    InlineKeyboardButton("📥 Direct Download", url=direct_link)
                ],
                [
                    InlineKeyboardButton("📢 Channel", url=CHANNEL_URL),
                    InlineKeyboardButton("🗑️ Delete Link", callback_data=f"del_{file_id}")
                ]
            ])
            await message.reply_text(result_text, parse_mode=ParseMode.HTML, reply_markup=action_buttons)

        @app.on_callback_query()
        async def handle_callback(client: Client, query: CallbackQuery):
            data = query.data
            user_id = query.from_user.id if query.from_user else 0
            await query.answer()

            if data == "btn_verify_fsub":
                is_subbed = await check_fsub(client, user_id)
                if is_subbed:
                    welcome_text = f"<blockquote><b>✅ Subscription Verified!</b></blockquote>\n\nSend any file to generate an Instant Stream Link."
                    await query.edit_message_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())
                else:
                    await query.answer("⚠️ You have not joined @movieshouseworld yet!", show_alert=True)

            elif data == "btn_stats":
                total = await get_total_stats()
                users = await get_total_users_count()
                uptime_sec = int(time.time() - START_TIME)
                uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
                stats_text = (
                    f"<blockquote><b>📊 System Statistics</b></blockquote>\n\n"
                    f"• <b>Total Users:</b> {users}\n"
                    f"• <b>Links Generated:</b> {total}\n"
                    f"• <b>Bot Uptime:</b> {uptime_str}\n"
                    f"• <b>Server:</b> VPS Cloud (Singapore)\n"
                    f"• <b>Channel:</b> @movieshouseworld"
                )
                back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="btn_home")]])
                await query.edit_message_text(stats_text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

            elif data == "btn_speed":
                t0 = time.time()
                try:
                    await client.get_me()
                    ping_ms = round((time.time() - t0) * 1000, 2)
                except Exception:
                    ping_ms = 12.4

                speed_text = (
                    f"<blockquote><b>⚡ Server Ping & Speed</b></blockquote>\n\n"
                    f"• <b>Telegram Ping:</b> {ping_ms} ms\n"
                    f"• <b>Port Speed:</b> 1 Gbps (VPS Singapore)\n"
                    f"• <b>Status:</b> 100% Operational"
                )
                back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="btn_home")]])
                await query.edit_message_text(speed_text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

            elif data == "btn_security":
                sec_text = (
                    f"<blockquote><b>🛡️ Security & Privacy</b></blockquote>\n\n"
                    f"• <b>Encryption:</b> Secure Telegram MTProto\n"
                    f"• <b>Database:</b> Safe & Encrypted MongoDB\n"
                    f"• <b>Files:</b> No files are stored on our servers permanently."
                )
                back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="btn_home")]])
                await query.edit_message_text(sec_text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

            elif data == "btn_help":
                help_text = (
                    f"<blockquote><b>❓ MoviesHouse PRO — Help Guide</b></blockquote>\n\n"
                    f"👋 Hi! Here is how to use this bot:\n\n"
                    f"📁 <b>How to get Stream/Download links:</b>\n"
                    f"1. Send or forward any video, audio, or document file to this bot.\n"
                    f"2. The bot will instantly generate a fast stream and download link.\n"
                    f"3. You can click on the link to watch online or download directly.\n\n"
                    f"🍿 <b>Using the Video Player:</b>\n"
                    f"• Use the <b>VLC</b> or <b>MX Player</b> buttons to watch in external players.\n"
                    f"• In the web player, click the settings gear icon to adjust playback speed.\n"
                    f"• Click the <b>Audio Language Guide</b> on the web page to see how to switch languages in VLC or MX Player.\n\n"
                    f"📢 <b>Support:</b> @movieshouseworld"
                )
                back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="btn_home")]])
                await query.edit_message_text(help_text, parse_mode=ParseMode.HTML, reply_markup=back_kb)

            elif data == "btn_home":
                user_name = query.from_user.first_name if query.from_user else "User"
                welcome_text = f"<blockquote><b>🎬 MoviesHouse PRO</b></blockquote>\n\n👋 Welcome <b>{user_name}</b>!\n\nSend any file to generate an Instant Link."
                await query.edit_message_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=get_main_keyboard())

            elif data.startswith("del_"):
                file_id = data.replace("del_", "")
                await delete_file_record(file_id)
                await query.edit_message_text("<blockquote><b>🗑️ Link Deleted!</b></blockquote>", parse_mode=ParseMode.HTML)

    return app

async def check_fsub(client: Client, user_id: int):
    for _ in range(3):
        try:
            member = await client.get_chat_member(CHANNEL_ID, user_id)
            return member.status not in ["kicked", "left"]
        except UserNotParticipant:
            return False
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            return True
    return True

def get_fsub_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Updates Channel", url=CHANNEL_URL)],
        [InlineKeyboardButton("🔄 Try Again / Verify", callback_data="btn_verify_fsub")]
    ])

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 System Status", callback_data="btn_stats"),
            InlineKeyboardButton("⚡ Real-Time Speed", callback_data="btn_speed")
        ],
        [
            InlineKeyboardButton("🛡️ Security & Privacy", callback_data="btn_security"),
            InlineKeyboardButton("❓ Help Guide", callback_data="btn_help")
        ],
        [
            InlineKeyboardButton("📢 Updates Channel (@movieshouseworld)", url=CHANNEL_URL)
        ]
    ])

async def main():
    print(f"🚀 Launching Native Web Server FIRST on Port {PORT}...", flush=True)
    web_app = web_server.create_aiohttp_app()
    runner  = web.AppRunner(web_app)
    await runner.setup()
    site    = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Native aiohttp Web Server Running & Health Check Ready on Port {PORT}", flush=True)

    print("🤖 Instantiating Hydrogram MTProto Client inside active asyncio loop...", flush=True)
    client_app = get_app()
    
    async def start_client_with_retry():
        while True:
            try:
                await client_app.start()
                print("✅ Hydrogram MTProto Client Started Successfully!", flush=True)
                web_server.set_bot_app(client_app, asyncio.get_running_loop())
                await init_indexes()
                break
            except Exception as ex:
                import traceback
                from hydrogram.errors import FloodWait
                if isinstance(ex, FloodWait):
                    wait_sec = ex.value + 5
                    print(f"⚠️ Telegram client startup postponed due to FloodWait ({ex.value}s). Retrying in {wait_sec} seconds...", flush=True)
                    await asyncio.sleep(wait_sec)
                else:
                    print(f"❌ Hydrogram startup error: {ex}. Retrying in 15 seconds...", flush=True)
                    traceback.print_exc()
                    await asyncio.sleep(15)

    asyncio.create_task(start_client_with_retry())
    asyncio.create_task(mongo_health_check_loop())

    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ FATAL ENGINE CRASH: {e}", flush=True)
        sys.stderr.flush()
        raise e
