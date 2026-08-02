import os
import re
import time
import asyncio
import logging
from aiohttp import web
from db_manager import get_file_record

logger = logging.getLogger("aiohttp_server")
bot_app = None

# Message reference cache with 15-minute TTL & automatic periodic eviction loop
msg_cache = {}
CACHE_TTL = 900 # 15 minutes in seconds

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
    html = """<!DOCTYPE html><html><head><title>MoviesHouse PRO</title></head>
<body style="background:#0f172a;color:#f8fafc;text-align:center;padding:50px;font-family:system-ui;">
  <h1 style="color:#10b981;">&#127916; MoviesHouse PRO</h1>
  <p style="color:#94a3b8;">Enterprise Message-Cached Streaming Engine</p>
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

    template_path = os.path.join(os.path.dirname(__file__), "templates", "download.html")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            template_content = f.read()
        html = (template_content
                .replace("{{ file_name }}", file_name)
                .replace("{{ file_size }}", f"{file_size_mb:.2f}")
                .replace("{{ mime_type }}", mime_type)
                .replace("{{ file_id }}", file_id))
        return web.Response(text=html, content_type="text/html")

    html = f"""<!DOCTYPE html><html><head><title>{file_name}</title></head>
<body style="background:#090d16;color:#fff;text-align:center;padding:40px;font-family:sans-serif;">
  <h2>🎬 MoviesHouse PRO</h2>
  <h3>{file_name} ({file_size_mb:.2f} MB)</h3>
  <br>
  <a href="/file/{file_id}" style="background:#10b981;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">⬇️ Direct Download / Stream</a>
</body></html>"""
    return web.Response(text=html, content_type="text/html")

async def handle_serve_file(request):
    file_id = request.match_info.get("file_id", "")
    if not re.match(r"^[a-zA-Z0-9\-]{4,64}$", file_id):
        raise web.HTTPBadRequest()

    file_info = await get_file_record(file_id)
    if not file_info:
        raise web.HTTPNotFound()

    total_size = file_info.get("file_size", 0)
    mime       = file_info.get("mime_type", "video/mp4")
    fname      = file_info.get("file_name", "video.mp4")
    chat_id    = file_info.get("chat_id")
    msg_id     = file_info.get("message_id")
    tg_file_id = file_info.get("tg_file_id")

    if not bot_app:
        raise web.HTTPServiceUnavailable()

    range_header = request.headers.get("Range", None)
    start_offset = 0
    end_offset   = total_size - 1 if total_size else None
    is_range     = False

    if range_header and total_size:
        is_range = True
        byte_range = range_header.replace("bytes=", "").strip()
        parts = byte_range.split("-")
        start_offset = int(parts[0]) if parts[0] else 0
        end_offset   = int(parts[1]) if len(parts) > 1 and parts[1] else total_size - 1

    chunk_size       = 1024 * 1024
    offset_chunks    = start_offset // chunk_size
    first_chunk_skip = start_offset % chunk_size

    status = 206 if is_range else 200
    headers = {
        "Content-Type":        mime,
        "Content-Disposition": f'inline; filename="{fname}"',
        "Accept-Ranges":       "bytes",
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

    # ⚡ Check Message Object Cache (0ms Instant Reuse)
    target = tg_file_id
    now = time.time()

    if file_id in msg_cache and (now - msg_cache[file_id]['ts'] < CACHE_TTL):
        target = msg_cache[file_id]['msg']
    elif chat_id and msg_id:
        try:
            msg = await bot_app.get_messages(chat_id, msg_id)
            if msg:
                target = msg
                msg_cache[file_id] = {'msg': msg, 'ts': now}
        except Exception:
            pass

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

def create_aiohttp_app():
    app = web.Application()
    app.on_startup.append(cleanup_cache_task)
    app.router.add_get("/", handle_home)
    app.router.add_get("/dl/{file_id}", handle_download_page)
    app.router.add_get("/download/{file_id}", handle_download_page)
    app.router.add_get("/file/{file_id}", handle_serve_file)
    return app
