# download_client.py - Apna Khud Ka Download Client

import os
import tempfile
import asyncio
from pyrogram import Client
from info import API_ID, API_HASH, BOT_TOKEN

# ============================================================
# GLOBAL VARIABLES
# ============================================================
_download_client = None
_download_client_started = False

# ============================================================
# CLIENT START / GET
# ============================================================
async def get_client():
    """
    Get or create download client
    """
    global _download_client, _download_client_started
    
    if not _download_client:
        try:
            print("🔄 Creating new download client...")
            _download_client = Client(
                name="download_bot",
                api_id=API_ID,
                api_hash=API_HASH,
                bot_token=BOT_TOKEN,
                in_memory=True
            )
            await _download_client.start()
            _download_client_started = True
            print("✅ Download Client Started Successfully!")
        except Exception as e:
            print(f"❌ Error starting download client: {e}")
            return None
    
    return _download_client

# ============================================================
# DOWNLOAD FILE FUNCTION
# ============================================================
async def download_file(file_id, custom_name=None):
    """
    Download file from Telegram
    """
    try:
        client = await get_client()
        if not client:
            print("❌ No client available!")
            return None
        
        # Create temp file
        suffix = '.mp4'
        if custom_name:
            ext = os.path.splitext(custom_name)[1]
            if ext:
                suffix = ext
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
        
        print(f"📥 Downloading file: {file_id[:20]}...")
        print(f"📁 Temp path: {temp_path}")
        
        # Download the file
        downloaded = await client.download_media(
            message=file_id,
            file_name=temp_path
        )
        
        if downloaded and os.path.exists(downloaded):
            file_size = os.path.getsize(downloaded)
            print(f"✅ Download successful! Size: {file_size} bytes")
            return downloaded
        else:
            print("❌ Download failed! File not found.")
            return None
            
    except Exception as e:
        print(f"❌ Download error: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================
# GET FILE INFO FUNCTION
# ============================================================
async def get_file_info(file_id):
    """
    Get file information from Telegram
    """
    try:
        client = await get_client()
        if not client:
            return None
        
        msg = await client.get_messages(
            chat_id='me',
            message_ids=file_id
        )
        
        if msg and msg.media:
            media_type = msg.media.value
            media = getattr(msg, media_type)
            
            return {
                'file_id': media.file_id,
                'file_unique_id': media.file_unique_id,
                'file_name': getattr(media, 'file_name', 'unknown'),
                'file_size': getattr(media, 'file_size', 0),
                'mime_type': getattr(media, 'mime_type', 'video/mp4'),
                'duration': getattr(media, 'duration', 0),
                'width': getattr(media, 'width', 0),
                'height': getattr(media, 'height', 0)
            }
        else:
            print("❌ No media found in message!")
            return None
            
    except Exception as e:
        print(f"❌ Get file info error: {e}")
        return None

# ============================================================
# CLOSE CLIENT FUNCTION
# ============================================================
async def close_client():
    """
    Close the download client
    """
    global _download_client, _download_client_started
    
    if _download_client and _download_client_started:
        try:
            await _download_client.stop()
            _download_client = None
            _download_client_started = False
            print("❌ Download Client Closed!")
        except Exception as e:
            print(f"❌ Error closing client: {e}")

# ============================================================
# CLEANUP FUNCTION
# ============================================================
def cleanup_temp_file(file_path):
    """
    Delete temporary file
    """
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Temp file deleted: {file_path}")
            return True
    except Exception as e:
        print(f"❌ Cleanup error: {e}")
    return False
