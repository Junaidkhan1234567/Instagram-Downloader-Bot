import asyncio
import os
import sqlite3
import time
import re
from contextlib import closing
from typing import List
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import CommandStart, Command
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
API_URL = os.getenv("API_URL", "https://vkrdownloader.xyz/server/")
API_KEY = os.getenv("API_KEY", "vkrdownloader")
DB_FILE = "users.db"

# Initialize database
def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()

# Database functions
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

# Instagram media fetch function
async def fetch_insta_media(link: str) -> dict | None:
    params = {"api_key": API_KEY, "vkr": link}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(API_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("data") or not data["data"].get("downloads"):
                return None
            return data
    except Exception as e:
        print(f"Error fetching media: {e}")
        return None

# Download video with progress
async def download_with_progress(url: str, msg: Message, label: str) -> bytes | None:
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
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
        print(f"Download error: {e}")
        return None

# Initialize bot
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Start command
@dp.message(CommandStart())
async def cmd_start(message: Message):
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
        "<b>How to use:</b>\n"
        "1. Copy Instagram URL\n"
        "2. Paste and send here\n"
        "3. Wait for download\n\n"
        "⚠️ Only public videos work!"
    )

# Help command
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Help Guide</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/stats - Show user stats (Admin only)\n"
        "/bcast - Broadcast message (Admin only)\n\n"
        "<b>Supported Links:</b>\n"
        "• https://www.instagram.com/reel/...\n"
        "• https://www.instagram.com/p/...\n"
        "• https://www.instagram.com/tv/...\n\n"
        "Just send any Instagram link and I'll handle the rest! 🚀"
    )

# Stats command (admin only)
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ You are not authorized to use this command.")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

# Broadcast command (admin only)
@dp.message(Command("bcast"))
async def cmd_bcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ You are not authorized to use this command.")
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

# Main handler - Instagram URL
@dp.message(F.text)
async def handle_instagram_url(message: Message):
    text = message.text.strip()
    
    # Check if it's an Instagram URL
    instagram_patterns = [
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:reel|p|tv)\/[A-Za-z0-9_-]+',
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/[A-Za-z0-9_.]+\/?$'
    ]
    
    is_instagram = any(re.search(pattern, text) for pattern in instagram_patterns)
    
    if not is_instagram:
        return
    
    wait_msg = await message.reply("⏳ <b>Fetching media...</b>")
    
    try:
        data = await fetch_insta_media(text)
        if not data:
            await wait_msg.edit_text("❌ <b>Error:</b> Could not fetch media. Make sure the URL is public.")
            return
        
        downloads = data["data"]["downloads"]
        if not downloads:
            await wait_msg.edit_text("❌ <b>Error:</b> No media found in this post.")
            return
        
        best_video = None
        best_quality = 0
        
        for item in downloads:
            url = item.get("url")
            if not url:
                continue
            ext = (item.get("ext") or "mp4").lower()
            if ext in {"mp4", "webm"}:
                quality_str = item.get("quality", "unknown")
                quality_score = 0
                if "1080" in quality_str:
                    quality_score = 3
                elif "720" in quality_str:
                    quality_score = 2
                elif "480" in quality_str:
                    quality_score = 1
                
                if quality_score >= best_quality:
                    best_quality = quality_score
                    best_video = url
        
        if not best_video:
            await wait_msg.edit_text("❌ <b>Error:</b> No video found. This might be a photo post.")
            return
        
        await wait_msg.edit_text("📥 <b>Downloading video...</b>")
        video_bytes = await download_with_progress(best_video, wait_msg, "📥 Downloading")
        
        if not video_bytes:
            await wait_msg.edit_text("❌ <b>Error:</b> Download failed. Please try again.")
            return
        
        await wait_msg.edit_text("📤 <b>Uploading video...</b>")
        
        caption = data["data"].get("caption", "")
        if caption:
            caption = caption[:200] + "..." if len(caption) > 200 else caption
        
        video_file = BufferedInputFile(video_bytes, filename="instagram_video.mp4")
        
        try:
            await message.reply_video(
                video_file,
                caption=f"📹 <b>Downloaded Successfully!</b>\n\n{caption}" if caption else "✅ <b>Video Downloaded!</b>",
                supports_streaming=True
            )
            await wait_msg.delete()
        except Exception as e:
            if "message is too long" in str(e).lower() or "file is too big" in str(e).lower():
                await wait_msg.edit_text("📦 <b>Video is large, sending as file...</b>")
                await message.reply_document(
                    video_file,
                    caption="📹 <b>Video Downloaded!</b>"
                )
                await wait_msg.delete()
            else:
                raise e
                
    except Exception as e:
        error_msg = str(e)
        if "413" in error_msg or "too large" in error_msg.lower():
            await wait_msg.edit_text("❌ <b>Error:</b> Video file is too large (>50MB). Telegram limit exceeded.")
        else:
            await wait_msg.edit_text(f"❌ <b>Error:</b> Something went wrong. Please try again.\n\n<code>{error_msg[:100]}</code>")
        print(f"Error in handle_instagram_url: {e}")

# Main function
async def main():
    print("🤖 Bot starting...")
    init_db()
    print("✅ Database initialized")
    print(f"📊 Admin IDs: {ADMIN_IDS}")
    print("🚀 Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
