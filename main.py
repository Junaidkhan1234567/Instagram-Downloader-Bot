import asyncio
import os
import sys
import sqlite3
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

print("=" * 50)
print("🤖 Instagram Downloader Bot")
print("=" * 50)

# ===== CONFIGURATION =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
WEB_URL = os.getenv("WEB_URL", "https://instagram-downloader-web.onrender.com")
DB_FILE = "users.db"

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN not set!")
    sys.exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:10]}...")
print(f"✅ ADMIN_IDS: {ADMIN_IDS}")
print(f"✅ WEB_URL: {WEB_URL}")

# ===== DATABASE =====
def init_db():
    try:
        with closing(sqlite3.connect(DB_FILE)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.commit()
        print("✅ Database initialized")
    except Exception as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)

async def add_user(user_id: int, username: str | None, full_name: str):
    try:
        def _add():
            with closing(sqlite3.connect(DB_FILE)) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO users(user_id, username, full_name) VALUES(?,?,?)",
                    (user_id, username or "Unknown", full_name or "")
                )
                conn.commit()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _add)
    except Exception as e:
        print(f"⚠️ Database error: {e}")

async def get_all_users() -> List[int]:
    try:
        def _get():
            with closing(sqlite3.connect(DB_FILE)) as conn:
                return [row[0] for row in conn.execute("SELECT user_id FROM users").fetchall()]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)
    except Exception as e:
        print(f"⚠️ Database error: {e}")
        return []

# ===== INSTAGRAM VIDEO DOWNLOAD =====

async def get_instagram_video_url(instagram_url: str) -> str | None:
    """Multiple FREE APIs से video URL निकालें"""
    
    if not instagram_url.startswith('http'):
        instagram_url = 'https://' + instagram_url
    
    print(f"📥 Processing: {instagram_url}")
    
    # Method 1: VKR Downloader
    try:
        print("🔄 Trying VKR Downloader...")
        vkr_url = "https://vkrdownloader.xyz/server/"
        params = {"api_key": "vkrdownloader", "vkr": instagram_url}
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(vkr_url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and data["data"].get("downloads"):
                    for item in data["data"]["downloads"]:
                        if item.get("url") and (".mp4" in item["url"] or ".webm" in item["url"]):
                            return item["url"]
    except Exception as e:
        print(f"⚠️ VKR error: {e}")
    
    # Method 2: SnapInsta
    try:
        print("🔄 Trying SnapInsta...")
        snap_url = "https://snapinsta.app/api/action"
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        payload = {"url": instagram_url}
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(snap_url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and data["data"].get("download"):
                    download = data["data"]["download"]
                    if isinstance(download, dict) and download.get("url"):
                        return download["url"]
                    elif isinstance(download, list) and len(download) > 0:
                        return download[0].get("url")
    except Exception as e:
        print(f"⚠️ SnapInsta error: {e}")
    
    # Method 3: SaveInsta
    try:
        print("🔄 Trying SaveInsta...")
        save_url = "https://saveinsta.app/api/action"
        headers = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
        payload = {"url": instagram_url}
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(save_url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("data") and data["data"].get("download"):
                    download = data["data"]["download"]
                    if isinstance(download, dict) and download.get("url"):
                        return download["url"]
                    elif isinstance(download, list) and len(download) > 0:
                        return download[0].get("url")
    except Exception as e:
        print(f"⚠️ SaveInsta error: {e}")
    
    print("❌ All methods failed!")
    return None

async def generate_download_link(instagram_url: str) -> str | None:
    """Download link generate करें"""
    try:
        video_url = await get_instagram_video_url(instagram_url)
        if not video_url:
            return None
        
        # Clean URL
        video_url = video_url.replace('\\/', '/')
        if video_url.startswith('//'):
            video_url = 'https:' + video_url
        
        encoded_url = quote(video_url, safe='')
        return f"{WEB_URL}/download?url={encoded_url}"
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return None

# ===== TELEGRAM BOT =====
try:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    print("✅ Bot created")
except Exception as e:
    print(f"❌ Bot creation failed: {e}")
    sys.exit(1)

# ===== COMMANDS =====

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name or ""
    )
    
    await message.answer(
        "🎬 <b>Instagram Video Downloader Bot</b>\n\n"
        "मुझे कोई भी Instagram URL भेजें और मैं आपको डाउनलोड लिंक दूंगा!\n\n"
        "<b>📌 कैसे उपयोग करें:</b>\n"
        "1️⃣ Instagram से Reel/Post का URL कॉपी करें\n"
        "2️⃣ यहां पेस्ट करें और भेजें\n"
        "3️⃣ मैं डाउनलोड लिंक जनरेट करूंगा\n"
        "4️⃣ <b>लिंक पर क्लिक करें → वीडियो डाउनलोड होगा</b>\n\n"
        "<b>✅ Supported:</b>\n"
        "• Reels (reel/)\n"
        "• Posts (p/)\n"
        "• Videos (tv/)\n\n"
        "<b>⚠️ Note:</b>\n"
        "सिर्फ <b>पब्लिक</b> पोस्ट काम करती हैं!"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Help Guide</b>\n\n"
        "<b>Commands:</b>\n"
        "/start - बॉट शुरू करें\n"
        "/help - यह हेल्प दिखाएं\n\n"
        "<b>📤 भेजें:</b>\n"
        "• Instagram Reel URL\n"
        "• Instagram Post URL\n"
        "• Instagram Video URL\n\n"
        "<b>उदाहरण:</b>\n"
        "<code>https://www.instagram.com/reel/ABC123/</code>\n"
        "<code>https://www.instagram.com/p/DEF456/</code>\n\n"
        "<b>💡 Tip:</b>\n"
        "अगर वीडियो नहीं मिलता, तो पोस्ट पब्लिक है या नहीं चेक करें।"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

@dp.message(F.text)
async def handle_instagram_url(message: Message):
    text = message.text.strip()
    
    patterns = [
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:reel|p|tv)\/[A-Za-z0-9_-]+',
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/[A-Za-z0-9_.]+\/?$',
    ]
    
    if not any(re.search(p, text, re.IGNORECASE) for p in patterns):
        return
    
    wait_msg = await message.reply("⏳ <b>डाउनलोड लिंक जनरेट हो रहा है...</b>")
    
    try:
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
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="⬇️ वीडियो डाउनलोड करें",
                    url=download_link
                )]
            ]
        )
        
        await wait_msg.edit_text(
            f"✅ <b>वीडियो मिल गया!</b>\n\n"
            f"📹 <b>डाउनलोड करने के लिए नीचे बटन पर क्लिक करें:</b>\n\n"
            f"🔗 <i>लिंक क्लिक करते ही डाउनलोड शुरू हो जाएगा</i>",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await wait_msg.edit_text(f"❌ <b>Error:</b> {str(e)[:100]}")

# ===== MAIN =====
async def main():
    print("=" * 50)
    print("🚀 Bot is running...")
    print("=" * 50)
    
    init_db()
    
    try:
        # ✅ IMPORTANT: Webhook clear करें
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook cleared")
        
        # Polling start करें
        await dp.start_polling(
            bot,
            polling_timeout=30,
            allowed_updates=["message", "callback_query"]
        )
    except Exception as e:
        print(f"❌ Bot error: {e}")
    finally:
        await bot.session.close()
        print("✅ Bot session closed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⚠️ Bot stopped")
