import asyncio
import os
import sqlite3
import time
import re
import logging
from contextlib import closing
from typing import List
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart, Command
from aiogram.enums.parse_mode import ParseMode
# ✅ FIX: Correct import path
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
DB_FILE = "users.db"

# ============= INSTAGRAM SCRAPING =============

async def fetch_instagram_video(url: str) -> dict | None:
    """Fetch Instagram video URL using multiple methods"""
    try:
        logger.info(f"Fetching video for URL: {url}")
        
        # Method 1: oEmbed API
        oembed_url = f"https://api.instagram.com/oembed?url={url}"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(oembed_url)
            if resp.status_code == 200:
                data = resp.json()
                thumbnail = data.get("thumbnail_url", "")
                if thumbnail:
                    video_url = thumbnail.replace(".jpg", ".mp4").replace("_n.jpg", "_n.mp4")
                    if video_url != thumbnail:
                        logger.info(f"Found video via oEmbed")
                        return {"url": video_url, "caption": data.get("title", "Instagram Video")}
        
        # Method 2: Direct scraping
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                html = resp.text
                patterns = [
                    r'(https?://[^\s"\']+\.mp4[^\s"\']*)',
                    r'(https?://[^\s"\']+video[^\s"\']+\.mp4[^\s"\']*)',
                    r'"video_url"\s*:\s*"([^"]+)"',
                ]
                for pattern in patterns:
                    matches = re.findall(pattern, html)
                    if matches:
                        for match in matches:
                            if match and '.mp4' in match:
                                logger.info(f"Found video via scraping")
                                return {"url": match, "caption": "Instagram Video"}
        
        logger.warning(f"No video found for URL: {url}")
        return None
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return None

# ============= DATABASE FUNCTIONS =============

def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()

async def add_user(user_id: int, username: str | None, full_name: str):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: sqlite3.connect(DB_FILE)
        .execute(
            "INSERT OR IGNORE INTO users(user_id, username, full_name) VALUES(?,?,?)",
            (user_id, username, full_name),
        )
        .connection.commit(),
    )

async def get_all_users() -> List[int]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: [
            row[0]
            for row in sqlite3.connect(DB_FILE)
            .execute("SELECT user_id FROM users")
            .fetchall()
        ],
    )

# ============= DOWNLOAD FUNCTIONS =============

async def download_with_progress(url: str, msg: Message, label: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
            }
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code not in [200, 206]:
                    return None
                total = int(resp.headers.get("content-length", 0))
                if total == 0:
                    return None
                chunks = b""
                start = time.time()
                last_update = 0
                done = 0
                async for chunk in resp.aiter_bytes(1024 * 64):
                    chunks += chunk
                    done += len(chunk)
                    now = time.time()
                    if now - last_update >= 2 and total > 0:
                        last_update = now
                        pct = int(done * 100 / total)
                        elapsed = now - start
                        eta = (total - done) * elapsed / done if done else 0
                        eta_str = f"{int(eta)}s" if eta < 3600 else f"{int(eta//60)}m"
                        try:
                            await msg.edit_text(f"{label} {pct}%  ETA: {eta_str}")
                        except Exception:
                            pass
                return chunks
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

# ============= TELEGRAM BOT =============

# ✅ FIX: Correct bot initialization
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    logger.info(f"✅ /start from user: {message.from_user.id}")
    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name or "",
    )
    await message.answer(
        "🎬 <b>Instagram Downloader Bot</b>\n\n"
        "Send me any Instagram link and I'll download the video for you!\n\n"
        "<b>Supported URLs:</b>\n"
        "📹 Instagram Reels\n"
        "📸 Instagram Posts\n"
        "🎥 Instagram Videos\n\n"
        "⚠️ Only public videos work!"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Help Guide</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/stats - Show user stats (Admin only)\n"
        "/bcast - Broadcast message (Admin only)\n\n"
        "Just send any Instagram link and I'll handle the rest! 🚀"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ You are not authorized.")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

@dp.message(Command("bcast"))
async def cmd_bcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ You are not authorized.")
        return
    text = message.text.partition(" ")[2]
    if not text:
        await message.answer("Usage: <code>/bcast Your message here</code>")
        return
    users = await get_all_users()
    sent = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Broadcast sent to <b>{sent}</b> users.")

@dp.message(F.text)
async def handle_instagram_url(message: Message):
    text = message.text.strip()
    logger.info(f"📩 Message from {message.from_user.id}: {text[:50]}...")
    
    # Check if it's an Instagram URL
    instagram_patterns = [
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:reel|p|tv)\/[A-Za-z0-9_-]+',
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/[A-Za-z0-9_.]+\/?$'
    ]
    
    is_instagram = any(re.search(pattern, text) for pattern in instagram_patterns)
    
    if not is_instagram:
        logger.info(f"⏭️ Not an Instagram URL")
        return
    
    logger.info(f"🔍 Processing Instagram URL")
    wait_msg = await message.reply("⏳ <b>Fetching media...</b>")
    
    try:
        result = await fetch_instagram_video(text)
        
        if not result or not result.get("url"):
            await wait_msg.edit_text(
                "❌ <b>Error:</b> Could not fetch media.\n\n"
                "Possible reasons:\n"
                "• URL might be private\n"
                "• Post might be deleted\n"
                "• Instagram API rate limit reached\n\n"
                "Try again with a public reel/post."
            )
            return
        
        video_url = result["url"]
        caption = result.get("caption", "Instagram Video")
        logger.info(f"✅ Video found")
        
        await wait_msg.edit_text("📥 <b>Downloading video...</b>")
        video_bytes = await download_with_progress(video_url, wait_msg, "📥 Downloading")
        
        if not video_bytes:
            await wait_msg.edit_text("❌ <b>Error:</b> Download failed. Please try again.")
            return
        
        logger.info(f"✅ Video downloaded: {len(video_bytes)} bytes")
        await wait_msg.edit_text("📤 <b>Uploading video...</b>")
        
        if caption and len(caption) > 200:
            caption = caption[:200] + "..."
        
        video_file = BufferedInputFile(video_bytes, filename="instagram_video.mp4")
        
        await message.reply_video(
            video_file,
            caption=f"📹 <b>Downloaded Successfully!</b>\n\n{caption}" if caption else "✅ <b>Video Downloaded!</b>",
            supports_streaming=True
        )
        await wait_msg.delete()
        logger.info(f"✅ Video sent to user")
                
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        await wait_msg.edit_text(f"❌ <b>Error:</b> Something went wrong. Please try again.\n\n<code>{str(e)[:100]}</code>")

# ============= MAIN =============

async def main():
    logger.info("🤖 Bot starting...")
    logger.info(f"📊 BOT_TOKEN: {BOT_TOKEN[:10]}... (length: {len(BOT_TOKEN) if BOT_TOKEN else 0})")
    
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN is not set!")
        return
    
    # Clear webhook
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Webhook cleared")
    
    init_db()
    logger.info("✅ Database initialized")
    
    # Test bot connection
    try:
        me = await bot.get_me()
        logger.info(f"✅ Bot connected: @{me.username}")
        logger.info(f"🆔 Bot ID: {me.id}")
    except Exception as e:
        logger.error(f"❌ Bot connection failed: {e}")
        return
    
    logger.info("🚀 Bot is running and polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
