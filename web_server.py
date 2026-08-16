import os
import re
import time
import json
import asyncio
import logging
from aiohttp import web
from db_manager import get_file_record, save_file_record

logger = logging.getLogger("aiohttp_server")
bot_app = None

# Message reference cache with 24-hour TTL & automatic periodic eviction loop
msg_cache = {}
CACHE_TTL = 86400 # 24 hours in seconds

def set_bot_app(instance, loop=None):
    global bot_app
    bot_app = instance

async def cleanup_cache_task(app):
    """Background task to evict expired items from msg_cache to prevent memory leaks."""
    async def loop_fn():
        while True:
            await asyncio.sleep(300) # Run every 5 minutes
            now = time.time()
            expired = [fid for fid, data in msg_cache.items() if now - data['ts'] > CACHE_TTL]
            for fid in expired:
                msg_cache.pop(fid, None)
    asyncio.create_task(loop_fn())

async def handle_home(request):
    """Stealth masked landing page for Render inspection compliance."""
    html = """<!DOCTYPE html><html><head><title>Cloud Utility API</title></head>
<body style="background:#0f172a;color:#f8fafc;text-align:center;padding:50px;font-family:system-ui;">
  <h1 style="color:#10b981;">⚡ Cloud Utility API Gateway</h1>
  <p style="color:#94a3b8;">Service Status: Operational & Healthy</p>
  <code style="color:#38bdf8;">v2.0.4 • High Performance Async Sockets</code>
</body></html>"""
    return web.Response(text=html, content_type="text/html")

async def handle_download_page(request):
    file_id = request.match_info.get("file_id", "")
    if not re.match(r"^[a-zA-Z0-9\-]{4,64}$", file_id):
        raise web.HTTPBadRequest()

    file_info = await get_file_record(file_id)
    if not file_info:
        raise web.HTTPNotFound()

    file_name = file_info.get("file_name", "file")
    file_size_mb = file_info.get("file_size", 0) / (1024 * 1024)
    mime_type = file_info.get("mime_type", "video/mp4")

    # Single Audio Mode: Empty tracks list
    display_tracks = []

    template_path = os.path.join(os.path.dirname(__file__), "templates", "download.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        html = (template_content
                .replace("{{ file_name }}", file_name)
                .replace("{{ file_size }}", f"{file_size_mb:.2f}")
                .replace("{{ mime_type }}", mime_type)
                .replace("{{ file_id }}", file_id)
                .replace("{{ track_query }}", "")
                .replace("{{ duration }}", str(file_info.get("duration") or "null"))
                .replace("{{ audio_tracks }}", "[]"))
        
        nocache_headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
        return web.Response(text=html, content_type="text/html", headers=nocache_headers)

    html = f"""<!DOCTYPE html><html><head><title>{file_name}</title></head>
<body style="background:#090d16;color:#fff;text-align:center;padding:40px;font-family:sans-serif;">
  <h2>🎬 Media Cloud</h2>
  <h3>{file_name} ({file_size_mb:.2f} MB)</h3>
  <br>
  <a href="/file/{file_id}" style="background:#10b981;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">⬇️ Direct Stream / Download</a>
</body></html>"""
    nocache_headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    return web.Response(text=html, content_type="text/html", headers=nocache_headers)

async def handle_serve_file(request):
    file_id = request.match_info.get("file_id", "")
    if not re.match(r"^[a-zA-Z0-9\-]{4,64}$", file_id):
        raise web.HTTPBadRequest()

    file_info = await get_file_record(file_id)
    if not file_info:
        raise web.HTTPNotFound()

    total_size = file_info.get("file_size")
    fname      = file_info.get("file_name", "video.mp4")
    mime       = file_info.get("mime_type", "video/mp4")
    chat_id    = file_info.get("chat_id")
    msg_id     = file_info.get("message_id")
    tg_file_id = file_info.get("tg_file_id")

    # Clean control characters and escape double quotes
    fname = "".join(ch for ch in fname if ord(ch) >= 32 and ch != "\x7f")
    fname = fname.replace('"', '\\"')
    if not fname:
        fname = "video.mp4"
    mime = "".join(ch for ch in mime if ord(ch) >= 32 and ch != "\x7f")
    if not mime:
        mime = "video/mp4"

    if not bot_app:
        raise web.HTTPServiceUnavailable()

    if request.query.get("transcode") == "1" or request.query.get("aac") == "1":
        return await handle_transcode_file(request, file_info, target=None)

    range_header = request.headers.get("Range", None)
    start_offset = 0
    end_offset   = total_size - 1 if total_size else None
    is_range     = False

    if range_header and total_size:
        is_range = True
        byte_range = range_header.replace("bytes=", "").strip()
        parts = byte_range.split("-")
        start_offset = int(parts[0]) if parts[0] else 0
        if len(parts) > 1 and parts[1]:
            end_offset = int(parts[1])
        else:
            end_offset = total_size - 1

        # Range bounds validation
        if start_offset >= total_size:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{total_size}"})
        end_offset = min(end_offset, total_size - 1)

    # Telegram Chunk Alignment (1MB chunks)
    chunk_size       = 1024 * 1024
    offset_chunks    = start_offset // chunk_size
    first_chunk_skip = start_offset % chunk_size

    status = 206 if is_range else 200
    headers = {
        "Content-Type":        mime,
        "Content-Disposition": f'inline; filename="{fname}"',
        "Accept-Ranges":       "bytes",
        "Cache-Control":       "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma":              "no-cache",
        "Expires":             "0"
    }

    if is_range and total_size and end_offset is not None:
        req_length = end_offset - start_offset + 1
        headers["Content-Range"]  = f"bytes {start_offset}-{end_offset}/{total_size}"
        headers["Content-Length"] = str(req_length)
    else:
        req_length = total_size
        if total_size:
            headers["Content-Length"] = str(total_size)

    response = web.StreamResponse(status=status, headers=headers)
    await response.prepare(request)

    # Secure Message Object Resolution with cache
    target = tg_file_id
    now = time.time()

    if file_id in msg_cache and (now - msg_cache[file_id]['ts'] < CACHE_TTL):
        target = msg_cache[file_id]['msg']
    elif chat_id and msg_id:
        try:
            msg = None
            try:
                msg = await bot_app.get_messages(chat_id, msg_id)
            except Exception:
                try:
                    await bot_app.get_chat(chat_id)
                except Exception:
                    pass
                try:
                    msg = await bot_app.get_messages(chat_id, msg_id)
                except Exception:
                    pass
            
            if not msg or getattr(msg, "empty", True):
                channel_id_env = os.getenv("CHANNEL_ID", "@movieshouseworld")
                try:
                    msg = await bot_app.get_messages(channel_id_env, msg_id)
                except Exception:
                    pass
            
            if msg and not getattr(msg, "empty", True):
                target = msg
                msg_cache[file_id] = {'msg': msg, 'ts': now}
        except Exception as ge:
            logger.error(f"Error resolving file reference: {ge}")

    bytes_written = 0
    skip_needed   = first_chunk_skip

    try:
        async for chunk in bot_app.stream_media(target, offset=offset_chunks):
            if skip_needed > 0:
                if len(chunk) <= skip_needed:
                    skip_needed -= len(chunk)
                    continue
                else:
                    chunk = chunk[skip_needed:]
                    skip_needed = 0

            # Trim chunk for requested byte range length
            if is_range and req_length:
                remaining = req_length - bytes_written
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]

            await response.write(chunk)
            bytes_written += len(chunk)

            if is_range and req_length and bytes_written >= req_length:
                break
    except Exception as e:
        logger.debug(f"Streaming finished: {e}")

    try:
        await response.write_eof()
    except Exception:
        pass
    return response

async def handle_transcode_file(request, file_info=None, target=None):
    file_id = request.match_info.get("file_id", "")
    if not file_info:
        file_info = await get_file_record(file_id)
        if not file_info:
            raise web.HTTPNotFound()

    fname = file_info.get("file_name", "video.mp4")
    fname = "".join(ch for ch in fname if ord(ch) >= 32 and ch != "\x7f").replace('"', '\\"')
    if not fname.lower().endswith(".mp4"):
        fname = os.path.splitext(fname)[0] + ".mp4"

    chat_id = file_info.get("chat_id")
    msg_id  = file_info.get("message_id")
    tg_file_id = file_info.get("tg_file_id")

    if not bot_app:
        raise web.HTTPServiceUnavailable()

    if not target:
        now = time.time()
        if file_id in msg_cache and (now - msg_cache[file_id]['ts'] < CACHE_TTL):
            target = msg_cache[file_id]['msg']
        elif chat_id and msg_id:
            try:
                msg = await bot_app.get_messages(chat_id, msg_id)
                if msg and not getattr(msg, "empty", True):
                    target = msg
                    msg_cache[file_id] = {'msg': msg, 'ts': now}
            except Exception:
                pass
        if not target:
            target = tg_file_id

    # FFmpeg Real-Time Transcoder: Video Copy (0% CPU), Audio to AAC Stereo (100% Browser Compatible)
    ffmpeg_cmd = [
        "ffmpeg", "-loglevel", "error",
        "-i", "pipe:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ac", "2",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1"
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
    except Exception as fe:
        logger.error(f"FFmpeg launch error: {fe}")
        raise web.HTTPInternalServerError()

    headers = {
        "Content-Type": "video/mp4",
        "Content-Disposition": f'inline; filename="{fname}"',
        "Cache-Control": "no-cache",
        "Access-Control-Allow-Origin": "*"
    }
    response = web.StreamResponse(status=200, headers=headers)
    await response.prepare(request)

    async def feed_ffmpeg():
        try:
            async for chunk in bot_app.stream_media(target):
                if proc.stdin and not proc.stdin.is_closing():
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
        except Exception as e:
            try:
                proc.kill()
            except Exception:
                pass

    feed_task = asyncio.create_task(feed_ffmpeg())

    try:
        while True:
            chunk = await proc.stdout.read(64 * 1024)
            if not chunk:
                break
            await response.write(chunk)
    except Exception as e:
        logger.debug(f"Transcode streaming client disconnected: {e}")
    finally:
        try:
            proc.kill()
        except Exception:
            pass
        await feed_task

    try:
        await response.write_eof()
    except Exception:
        pass
    return response

async def handle_api_metadata(request):
    file_id = request.match_info.get("file_id", "")
    if not re.match(r"^[a-zA-Z0-9\-]{4,64}$", file_id):
        return web.json_response({"error": "Invalid file ID"}, status=400)

    file_info = await get_file_record(file_id)
    if not file_info:
        return web.json_response({"error": "File not found"}, status=404)

    return web.json_response({
        "audio_tracks": [],
        "duration": file_info.get("duration")
    })

def create_aiohttp_app():
    app = web.Application()
    app.on_startup.append(cleanup_cache_task)
    app.router.add_get("/", handle_home)
    app.router.add_get("/dl/{file_id}", handle_download_page)
    app.router.add_get("/download/{file_id}", handle_download_page)
    app.router.add_get("/file/{file_id}", handle_serve_file)
    app.router.add_get("/transcode/{file_id}", handle_transcode_file)
    app.router.add_get("/dl/api/metadata/{file_id}", handle_api_metadata)
    return app
