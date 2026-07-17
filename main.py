import asyncio
import os
import sqlite3
import time
import re
from contextlib import closing
from typing import List
import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv
from urllib.parse import quote

load_dotenv()

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "8906591214:AAGBVds2mjAh5KQJyN3i0a8vnoWoNDLGlE0")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "1383239349").split(","))) if os.getenv("ADMIN_IDS") else []
WEB_URL = os.getenv("WEB_URL", "https://instagram-downloader-bot-rcuj.onrender.com")  # ⚠️ अपना Web URL डालें
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

# Generate download link function
async def generate_download_link(instagram_url: str) -> str | None:
    """Instagram URL से डाउनलोड लिंक जनरेट करें"""
    params = {"api_key": API_KEY, "vkr": instagram_url}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(API_URL, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("data") or not data["data"].get("downloads"):
                return None
            
            # Best video URL ढूंढें
            best_video = None
            best_quality = 0
            for item in data["data"]["downloads"]:
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
                return None
            
            # Web Server पर URL encode करके भेजें
            encoded_url = quote(best_video, safe='')
            download_link = f"{WEB_URL}/download?url={encoded_url}"
            return download_link
            
    except Exception as e:
        print(f"Error generating link: {e}")
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
    
    welcome_text = """
🎬 <b>Instagram Video Downloader Bot</b>

मुझे कोई भी Instagram URL भेजें और मैं आपको डाउनलोड लिंक दूंगा!

<b>📌 कैसे उपयोग करें:</b>
1️⃣ Instagram से Reel/Post का URL कॉपी करें
2️⃣ यहां पेस्ट करें और भेजें
3️⃣ मैं डाउनलोड लिंक जनरेट करूंगा
4️⃣ <b>लिंक पर क्लिक करें → वीडियो डाउनलोड होगा</b>

<b>✅ Supported:</b>
• Reels (reel/)
• Posts (p/)
• Videos (tv/)

<b>⚠️ Note:</b>
सिर्फ <b>पब्लिक</b> पोस्ट काम करती हैं!
"""
    await message.answer(welcome_text)

# Help command
@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = """
📖 <b>Help Guide</b>

<b>Commands:</b>
/start - बॉट शुरू करें
/help - यह हेल्प दिखाएं

<b>📤 भेजें:</b>
• Instagram Reel URL
• Instagram Post URL
• Instagram Video URL

<b>उदाहरण:</b>
<code>https://www.instagram.com/reel/ABC123/</code>
<code>https://www.instagram.com/p/DEF456/</code>

<b>🔗 फिर:</b>
मैं आपको डाउनलोड लिंक दूंगा → क्लिक करें → डाउनलोड शुरू!

<b>💡 Tip:</b>
अगर वीडियो नहीं मिलता, तो पोस्ट पब्लिक है या नहीं चेक करें।
"""
    await message.answer(help_text)

# Stats command (admin only)
@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

# Broadcast command (admin only)
@dp.message(Command("bcast"))
async def cmd_bcast(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
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
    
    # Instagram URL check
    instagram_patterns = [
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:reel|p|tv)\/[A-Za-z0-9_-]+',
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/[A-Za-z0-9_.]+\/?$'
    ]
    
    is_instagram = any(re.search(pattern, text) for pattern in instagram_patterns)
    
    if not is_instagram:
        return
    
    # Show loading
    wait_msg = await message.reply("⏳ <b>डाउनलोड लिंक जनरेट हो रहा है...</b>")
    
    try:
        # Generate download link
        download_link = await generate_download_link(text)
        
        if not download_link:
            await wait_msg.edit_text(
                "❌ <b>Error:</b> वीडियो नहीं मिला!\n\n"
                "⚠️ सुनिश्चित करें:\n"
                "• URL सही है\n"
                "• पोस्ट <b>पब्लिक</b> है\n"
                "• वीडियो मौजूद है"
            )
            return
        
        # Create inline button
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬇️ वीडियो डाउनलोड करें",
                    url=download_link
                )]
            ]
        )
        
        # Send message with download button
        await wait_msg.edit_text(
            f"✅ <b>वीडियो मिल गया!</b>\n\n"
            f"📹 <b>डाउनलोड करने के लिए नीचे बटन पर क्लिक करें:</b>\n\n"
            f"🔗 <i>लिंक क्लिक करते ही डाउनलोड शुरू हो जाएगा</i>",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ <b>Error:</b> कुछ गलत हो गया!\n\n"
            f"<code>{str(e)[:100]}</code>"
        )
        print(f"Error: {e}")

# Main function
async def main():
    print("🤖 Bot starting...")
    init_db()
    print("✅ Database initialized")
    print(f"📊 Admin IDs: {ADMIN_IDS}")
    print(f"🌐 Web URL: {WEB_URL}")
    print("🚀 Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
