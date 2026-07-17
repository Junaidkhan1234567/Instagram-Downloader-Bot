import asyncio
import os
import sqlite3
import time
import re
import json
import base64
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
DB_FILE = "users.db"

# ============= INSTAGRAM GRAPHQL API SCRAPING =============

class InstagramScraper:
    def __init__(self):
        self.base_url = "https://www.instagram.com"
        self.api_url = "https://www.instagram.com/api/graphql"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '129477',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
        }
        self.csrf_token = None
        self.session = None
    
    async def get_csrf_token(self, client):
        """Get CSRF token from Instagram"""
        try:
            resp = await client.get(self.base_url, headers=self.headers)
            if 'csrf_token' in resp.cookies:
                self.csrf_token = resp.cookies['csrf_token']
                self.headers['X-CSRFToken'] = self.csrf_token
            return True
        except:
            return False
    
    async def get_post_id(self, url: str) -> str:
        """Extract post ID from URL"""
        patterns = [
            r'/reel/([A-Za-z0-9_-]+)',
            r'/p/([A-Za-z0-9_-]+)',
            r'/tv/([A-Za-z0-9_-]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    async def fetch_video_url(self, url: str) -> dict | None:
        """Fetch video URL using multiple methods"""
        try:
            # Method 1: Get from Instagram oEmbed API
            result = await self.fetch_via_oembed(url)
            if result:
                return result
            
            # Method 2: Get from GraphQL API
            result = await self.fetch_via_graphql(url)
            if result:
                return result
            
            # Method 3: Get from public CDN
            result = await self.fetch_via_cdn(url)
            if result:
                return result
            
            return None
            
        except Exception as e:
            print(f"Error fetching video: {e}")
            return None
    
    async def fetch_via_oembed(self, url: str) -> dict | None:
        """Fetch video using Instagram oEmbed API"""
        try:
            oembed_url = f"https://api.instagram.com/oembed?url={url}"
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(oembed_url)
                if resp.status_code == 200:
                    data = resp.json()
                    # Try to get video from thumbnail
                    thumbnail = data.get("thumbnail_url", "")
                    if thumbnail:
                        # Convert thumbnail to video URL
                        video_url = thumbnail.replace(".jpg", ".mp4")
                        video_url = video_url.replace("_n.jpg", "_n.mp4")
                        if video_url != thumbnail:
                            return {
                                "url": video_url,
                                "caption": data.get("title", "Instagram Video"),
                                "type": "video"
                            }
            return None
        except:
            return None
    
    async def fetch_via_graphql(self, url: str) -> dict | None:
        """Fetch video using Instagram GraphQL API"""
        try:
            post_id = await self.get_post_id(url)
            if not post_id:
                return None
            
            # GraphQL query for video
            query = """
            query GetVideo($id: String!) {
                ig_shortcode(shortcode: $id) {
                    __typename
                    display_url
                    video_url
                    edge_media_to_caption {
                        edges {
                            node {
                                text
                            }
                        }
                    }
                    edge_media_preview_like {
                        count
                    }
                    owner {
                        username
                        full_name
                    }
                }
            }
            """
            
            # Try different API endpoints
            endpoints = [
                "https://www.instagram.com/graphql/query",
                "https://www.instagram.com/api/graphql",
                "https://www.instagram.com/query",
            ]
            
            variables = {"id": post_id}
            
            # Headers for GraphQL
            headers = {
                'User-Agent': self.headers['User-Agent'],
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-IG-App-ID': '936619743392459',
            }
            
            async with httpx.AsyncClient(timeout=30, headers=headers) as client:
                for endpoint in endpoints:
                    try:
                        resp = await client.post(
                            endpoint,
                            json={
                                "query": query,
                                "variables": variables,
                            }
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            # Extract video URL from response
                            if "data" in data and "ig_shortcode" in data["data"]:
                                video_data = data["data"]["ig_shortcode"]
                                if video_data.get("video_url"):
                                    caption = ""
                                    if video_data.get("edge_media_to_caption", {}).get("edges"):
                                        caption = video_data["edge_media_to_caption"]["edges"][0]["node"]["text"]
                                    return {
                                        "url": video_data["video_url"],
                                        "caption": caption or "Instagram Video",
                                        "type": "video"
                                    }
                    except:
                        continue
            
            return None
            
        except Exception as e:
            print(f"GraphQL error: {e}")
            return None
    
    async def fetch_via_cdn(self, url: str) -> dict | None:
        """Fetch video from Instagram CDN"""
        try:
            post_id = await self.get_post_id(url)
            if not post_id:
                return None
            
            # Try common CDN patterns
            cdn_patterns = [
                f"https://cdninstagram.com/video/{post_id}.mp4",
                f"https://instagram.fsof2-1.fna.fbcdn.net/v/t50.2886-16/{post_id}.mp4",
                f"https://video.cdninstagram.com/video/{post_id}.mp4",
            ]
            
            async with httpx.AsyncClient(timeout=30) as client:
                for cdn_url in cdn_patterns:
                    try:
                        resp = await client.head(cdn_url)
                        if resp.status_code == 200:
                            return {
                                "url": cdn_url,
                                "caption": "Instagram Video",
                                "type": "video"
                            }
                    except:
                        continue
            
            return None
            
        except Exception as e:
            print(f"CDN error: {e}")
            return None

# Initialize scraper
scraper = InstagramScraper()

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
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Range': 'bytes=0-',
            }
            async with client.stream("GET", url, headers=headers) as resp:
                if resp.status_code != 200 and resp.status_code != 206:
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

# ============= TELEGRAM BOT =============

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

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
        "⚠️ Only public videos work!\n\n"
        "⚡ Using GraphQL API (More Reliable)"
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
        "<b>Supported Links:</b>\n"
        "• https://www.instagram.com/reel/...\n"
        "• https://www.instagram.com/p/...\n"
        "• https://www.instagram.com/tv/...\n\n"
        "Just send any Instagram link and I'll handle the rest! 🚀"
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ You are not authorized to use this command.")
        return
    users = await get_all_users()
    await message.answer(f"📊 <b>Total Users:</b> <code>{len(users)}</code>")

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
    
    wait_msg = await message.reply("⏳ <b>Fetching media via GraphQL API...</b>")
    
    try:
        # Fetch video using multiple methods
        result = await scraper.fetch_video_url(text)
        
        if not result or not result.get("url"):
            await wait_msg.edit_text(
                "❌ <b>Error:</b> Could not fetch media.\n\n"
                "Possible reasons:\n"
                "• URL might be private\n"
                "• Post might be deleted\n"
                "• Instagram API rate limit reached\n\n"
                "Try again with a public reel/post.\n"
                "⚠️ Note: Some Instagram reels may not be accessible."
            )
            return
        
        video_url = result["url"]
        caption = result.get("caption", "Instagram Video")
        
        await wait_msg.edit_text("📥 <b>Downloading video...</b>")
        video_bytes = await download_with_progress(video_url, wait_msg, "📥 Downloading")
        
        if not video_bytes:
            await wait_msg.edit_text("❌ <b>Error:</b> Download failed. Please try again.")
            return
        
        await wait_msg.edit_text("📤 <b>Uploading video...</b>")
        
        if caption and len(caption) > 200:
            caption = caption[:200] + "..."
        
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

async def main():
    print("🤖 Bot starting...")
    print("📦 Using Instagram GraphQL API Scraping")
    init_db()
    print("✅ Database initialized")
    print(f"📊 Admin IDs: {ADMIN_IDS}")
    print("🚀 Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
