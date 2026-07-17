import asyncio
import os
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
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv
from urllib.parse import quote
import signal
import sys
import json
import base64
from bs4 import BeautifulSoup
import re

load_dotenv()

# ===== CONFIGURATION =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []
WEB_URL = os.getenv("WEB_URL", "https://instagram-downloader-web.onrender.com")
DB_FILE = "users.db"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN not set! Please add it to .env file")

# ===== DATABASE =====
def init_db():
    with closing(sqlite3.connect(DB_FILE)) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        conn.commit()

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
        print(f"⚠️ Database error (add_user): {e}")

async def get_all_users() -> List[int]:
    try:
        def _get():
            with closing(sqlite3.connect(DB_FILE)) as conn:
                return [row[0] for row in conn.execute("SELECT user_id FROM users").fetchall()]
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _get)
    except Exception as e:
        print(f"⚠️ Database error (get_all_users): {e}")
        return []

# ===== INSTAGRAM WEB SCRAPING - NO API KEY =====

async def fetch_instagram_page(url: str) -> str | None:
    """Fetch Instagram page HTML"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0"
        }
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            
            if resp.status_code == 200:
                return resp.text
            else:
                print(f"⚠️ Page fetch failed: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"⚠️ Fetch error: {e}")
        return None

def extract_video_url_from_html(html: str) -> str | None:
    """Extract video URL from Instagram page HTML"""
    try:
        # Method 1: Find video URL in meta tags
        video_patterns = [
            r'<meta[^>]*property="og:video"[^>]*content="([^"]+)"',
            r'<meta[^>]*property="og:video:url"[^>]*content="([^"]+)"',
            r'"video_url":"([^"]+)"',
            r'"video_versions":\[{"url":"([^"]+)"',
            r'"video_download_url":"([^"]+)"',
            r'<video[^>]*src="([^"]+)"',
            r'"video":\[{"url":"([^"]+)"',
            r'"download_url":"([^"]+)"',
            r'"content_url":"([^"]+)"',
        ]
        
        for pattern in video_patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                if match and ('mp4' in match or 'video' in match):
                    # Clean URL
                    video_url = match.replace('\\/', '/')
                    if video_url.startswith('//'):
                        video_url = 'https:' + video_url
                    return video_url
        
        # Method 2: Find in script tags
        script_pattern = r'<script[^>]*>([^<]+)</script>'
        scripts = re.findall(script_pattern, html)
        
        for script in scripts:
            # Look for video URLs in script
            video_matches = re.findall(r'(https?://[^"\']+\.(?:mp4|webm|mov)[^"\']*)', script)
            if video_matches:
                for match in video_matches:
                    if 'instagram' in match or 'cdn' in match:
                        return match
        
        # Method 3: Find in JSON data
        json_pattern = r'window\._sharedData\s*=\s*({[^<]+});'
        json_match = re.search(json_pattern, html)
        
        if json_match:
            try:
                data = json.loads(json_match.group(1))
                # Search for video URL in JSON
                return search_json_for_video(data)
            except:
                pass
        
        return None
        
    except Exception as e:
        print(f"⚠️ Extraction error: {e}")
        return None

def search_json_for_video(obj, depth=0):
    """Recursively search JSON for video URL"""
    if depth > 10:
        return None
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                if '.mp4' in value.lower() or '.webm' in value.lower():
                    if 'instagram' in value or 'cdn' in value or 'video' in value:
                        return value
            else:
                result = search_json_for_video(value, depth + 1)
                if result:
                    return result
    elif isinstance(obj, list):
        for item in obj:
            result = search_json_for_video(item, depth + 1)
            if result:
                return result
    
    return None

async def get_instagram_video_direct(instagram_url: str) -> str | None:
    """Get video URL directly from Instagram page"""
    
    print(f"📥 Fetching: {instagram_url}")
    
    # Clean URL
    if not instagram_url.startswith('http'):
        instagram_url = 'https://' + instagram_url
    
    # Try to get the page
    html = await fetch_instagram_page(instagram_url)
    if not html:
        print("❌ Failed to fetch page")
        return None
    
    # Extract video URL
    video_url = extract_video_url_from_html(html)
    
    if video_url:
        print(f"✅ Found video: {video_url[:100]}...")
        return video_url
    
    # If not found, try alternative approach - use external service
    print("🔄 Trying alternative method...")
    
    # Use a free proxy service to fetch video
    try:
        # Try using a public Instagram video downloader service (no API key needed)
        download_services = [
            f"https://www.instagramsave.com/download?url={quote(instagram_url)}",
            f"https://insta-download.net/download?url={quote(instagram_url)}",
            f"https://snapinsta.app/download?url={quote(instagram_url)}"
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for service in download_services:
                try:
                    resp = await client.get(service, headers=headers)
                    if resp.status_code == 200:
                        # Try to extract video URL from response
                        video_match = re.search(r'(https?://[^"\']+\.mp4[^"\']*)', resp.text)
                        if video_match:
                            return video_match.group(1)
                except:
                    continue
    except Exception as e:
        print(f"⚠️ Alternative method failed: {e}")
    
    return None

async def generate_download_link(instagram_url: str) -> str | None:
    """Generate download link using web scraping"""
    
    try:
        # Get video URL
        video_url = await get_instagram_video_direct(instagram_url)
        
        if not video_url:
            return None
        
        # Encode URL
        encoded_url = quote(video_url, safe='')
        download_link = f"{WEB_URL}/download?url={encoded_url}"
        return download_link
        
    except Exception as e:
        print(f"⚠️ Error generating link: {e}")
        return None

# ===== TELEGRAM BOT =====
session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ===== GRACEFUL SHUTDOWN =====
async def shutdown(loop, signal=None):
    print(f"⚠️ Received exit signal {signal}...")
    await bot.session.close()
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    print("✅ Shutdown complete")
    sys.exit(0)

def handle_shutdown(signum, frame):
    loop = asyncio.get_event_loop()
    loop.create_task(shutdown(loop, signum))

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# ===== COMMANDS =====

@dp.message(CommandStart())
async def cmd_start(message: Message):
    await add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.full_name or ""
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

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ आपको इस कमांड का उपयोग करने की अनुमति नहीं है।")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

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
    if not users:
        await message.answer("❌ No users found in database.")
        return
    
    sent = 0
    failed = 0
    
    for uid in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            print(f"⚠️ Failed to send to {uid}: {e}")
    
    await message.answer(
        f"✅ Broadcast sent to <b>{sent}</b> users.\n"
        f"❌ Failed: <b>{failed}</b>"
    )

# ===== INSTAGRAM URL HANDLER =====
@dp.message(F.text)
async def handle_instagram_url(message: Message):
    text = message.text.strip()
    
    # Check if it's an Instagram URL
    instagram_patterns = [
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:reel|p|tv)\/[A-Za-z0-9_-]+',
        r'(?:https?:\/\/)?(?:www\.)?instagram\.com\/[A-Za-z0-9_.]+\/?$',
        r'(?:https?:\/\/)?(?:www\.)?ig\.\w+\/[A-Za-z0-9_-]+'
    ]
    
    is_instagram = any(re.search(pattern, text, re.IGNORECASE) for pattern in instagram_patterns)
    
    if not is_instagram:
        return
    
    # Show loading
    wait_msg = await message.reply("⏳ <b>डाउनलोड लिंक जनरेट हो रहा है...</b>\n🔍 Web scraping से वीडियो ढूंढा जा रहा है...")
    
    try:
        download_link = await generate_download_link(text)
        
        if not download_link:
            await wait_msg.edit_text(
                "❌ <b>Error:</b> वीडियो नहीं मिला!\n\n"
                "⚠️ सुनिश्चित करें:\n"
                "• URL सही है\n"
                "• पोस्ट <b>पब्लिक</b> है\n"
                "• वीडियो मौजूद है\n\n"
                "💡 <b>Tip:</b> कुछ देर बाद फिर try करें"
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
        
        await wait_msg.edit_text(
            f"✅ <b>वीडियो मिल गया!</b>\n\n"
            f"📹 <b>डाउनलोड करने के लिए नीचे बटन पर क्लिक करें:</b>\n\n"
            f"🔗 <i>लिंक क्लिक करते ही डाउनलोड शुरू हो जाएगा</i>",
            reply_markup=keyboard
        )
        
    except Exception as e:
        await wait_msg.edit_text(
            f"❌ <b>Error:</b> कुछ गलत हो गया!\n\n"
            f"<code>{str(e)[:100]}</code>\n\n"
            f"💡 कुछ देर बाद फिर से try करें"
        )
        print(f"⚠️ Error in handler: {e}")

# ===== MAIN =====
async def main():
    print("🤖 Bot starting...")
    print(f"🆔 Bot ID: {BOT_TOKEN.split(':')[0] if BOT_TOKEN else 'Unknown'}")
    
    init_db()
    print("✅ Database initialized")
    print(f"📊 Admin IDs: {ADMIN_IDS}")
    print(f"🌐 Web URL: {WEB_URL}")
    print("🚀 Bot is running...")
    print("📥 Using Web Scraping (No API Key needed)")
    
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook cleared")
        
        await dp.start_polling(
            bot,
            polling_timeout=30,
            handle_signals=False,
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
        print("⚠️ Bot stopped by user")
