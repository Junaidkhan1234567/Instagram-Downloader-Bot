from flask import Flask, request, send_file, render_template_string, jsonify
import requests
import os
import tempfile
import re
import time
from urllib.parse import unquote
import json

app = Flask(__name__)

# ============= INSTAGRAM SCRAPING FUNCTIONS =============

def extract_video_from_html(html: str) -> str | None:
    """Extract video URL from Instagram page HTML"""
    patterns = [
        r'(https?://[^\s"\']+\.mp4[^\s"\']*)',
        r'(https?://[^\s"\']+video[^\s"\']+\.mp4[^\s"\']*)',
        r'(https?://[^\s"\']+cdninstagram\.com[^\s"\']+\.mp4[^\s"\']*)',
        r'"video_url"\s*:\s*"([^"]+)"',
        r'"videoUrl"\s*:\s*"([^"]+)"',
        r'"video_versions"\s*:\s*\[[^\]]*"url"\s*:\s*"([^"]+)"',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html)
        if matches:
            for url in matches:
                if url and '.mp4' in url:
                    return url
    return None

def get_instagram_video_url(insta_url: str) -> str | None:
    """Get direct video URL from Instagram post URL"""
    try:
        # Method 1: Direct page scraping
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        
        response = requests.get(insta_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return None
        
        video_url = extract_video_from_html(response.text)
        if video_url:
            return video_url
        
        # Method 2: Try oEmbed API
        oembed_url = f"https://api.instagram.com/oembed?url={insta_url}"
        response = requests.get(oembed_url, timeout=30)
        if response.status_code == 200:
            data = response.json()
            thumbnail = data.get("thumbnail_url", "")
            if thumbnail:
                # Try to convert thumbnail to video URL
                possible_video = thumbnail.replace(".jpg", ".mp4").replace("_n.jpg", "_n.mp4")
                if possible_video != thumbnail:
                    # Check if video exists
                    head_response = requests.head(possible_video, timeout=10)
                    if head_response.status_code == 200:
                        return possible_video
        
        # Method 3: Try alternative API
        alt_api = f"https://api.instagram-downloader.com/api/download?url={insta_url}"
        try:
            response = requests.get(alt_api, timeout=30)
            if response.status_code == 200:
                data = response.json()
                video = data.get("url") or data.get("download_url")
                if video:
                    return video
        except:
            pass
        
        return None
        
    except Exception as e:
        print(f"Error fetching video: {e}")
        return None

# ============= HTML TEMPLATES =============

HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Video Downloader</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            margin: 0;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 24px;
            padding: 50px 40px;
            max-width: 550px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideUp 0.6s ease;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .icon { font-size: 64px; margin-bottom: 15px; }
        h1 { 
            color: #1a1a2e; 
            font-size: 28px; 
            margin-bottom: 8px;
            font-weight: 700;
        }
        .subtitle { 
            color: #666; 
            margin-bottom: 25px; 
            font-size: 15px;
            line-height: 1.6;
        }
        .input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .input-group input {
            flex: 1;
            padding: 14px 18px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 15px;
            outline: none;
            transition: all 0.3s;
        }
        .input-group input:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.1);
        }
        .input-group input::placeholder {
            color: #aaa;
        }
        .btn-primary {
            padding: 14px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            white-space: nowrap;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .btn-download {
            display: inline-block;
            padding: 15px 40px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 12px;
            font-weight: 600;
            font-size: 17px;
            transition: all 0.3s;
            margin: 15px 0 10px;
            border: none;
            cursor: pointer;
        }
        .btn-download:hover {
            background: #218838;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40,167,69,0.3);
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 5px solid #f3f3f3;
            border-top: 5px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading {
            display: none;
            padding: 20px 0;
        }
        .loading.active { display: block; }
        .result {
            display: none;
            padding: 15px 0;
            animation: fadeIn 0.5s ease;
        }
        .result.active { display: block; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .error {
            display: none;
            color: #dc3545;
            background: #f8d7da;
            padding: 15px;
            border-radius: 12px;
            margin: 15px 0;
            font-size: 14px;
        }
        .error.active { display: block; }
        .success {
            color: #28a745;
            background: #d4edda;
            padding: 15px;
            border-radius: 12px;
            margin: 10px 0;
            font-size: 16px;
        }
        .features {
            display: flex;
            gap: 15px;
            margin-top: 25px;
            flex-wrap: wrap;
            justify-content: center;
        }
        .feature-item {
            background: #f8f9fa;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 12px;
            color: #555;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .feature-item i { color: #667eea; }
        .footer { margin-top: 25px; color: #999; font-size: 12px; border-top: 1px solid #eee; padding-top: 20px; }
        @media (max-width: 600px) {
            .container { padding: 30px 20px; }
            .input-group { flex-direction: column; }
            .btn-primary { width: 100%; justify-content: center; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📥</div>
        <h1>Instagram Downloader</h1>
        <p class="subtitle">Instagram Reels, Videos, aur Posts Download karein</p>
        
        <div class="input-group">
            <input type="text" id="urlInput" placeholder="Instagram URL paste karein...">
            <button class="btn-primary" id="downloadBtn">⬇️ Download</button>
        </div>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>⏳ <b>Processing...</b></p>
            <p style="color: #666; font-size: 13px;">Video fetch ho raha hai...</p>
        </div>
        
        <div class="result" id="result">
            <div class="success">✅ <b>Video Ready!</b></div>
            <a href="#" id="downloadLink" class="btn-download">⬇️ Download Video</a>
            <p style="color: #666; font-size: 13px; margin-top: 8px;">Click karein download ke liye</p>
        </div>
        
        <div class="error" id="error"></div>
        
        <div class="features">
            <span class="feature-item">📹 Reels</span>
            <span class="feature-item">📸 Posts</span>
            <span class="feature-item">⚡ Fast</span>
            <span class="feature-item">🔒 Free</span>
        </div>
        
        <div class="footer">
            <p>🔒 सुरक्षित डाउनलोड | ⚡ तेज़</p>
            <p style="font-size: 11px; margin-top: 5px;">⚠️ Only public videos work</p>
        </div>
    </div>
    
    <script>
        document.getElementById('downloadBtn').addEventListener('click', function() {
            const urlInput = document.getElementById('urlInput');
            const url = urlInput.value.trim();
            
            if (!url) {
                showError('❌ Please enter a valid Instagram URL');
                return;
            }
            
            // Check if it's an Instagram URL
            const instagramPattern = /(?:https?:\\/\\/)?(?:www\\.)?instagram\\.com\\/(?:reel|p|tv)\\/[A-Za-z0-9_-]+/;
            if (!instagramPattern.test(url)) {
                showError('❌ Please enter a valid Instagram URL (reel/p/tv)');
                return;
            }
            
            // Show loading
            document.getElementById('loading').classList.add('active');
            document.getElementById('result').classList.remove('active');
            document.getElementById('error').classList.remove('active');
            this.disabled = true;
            this.textContent = '⏳ Processing...';
            
            // Send request to server
            fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url: url })
            })
            .then(response => response.json())
            .then(data => {
                document.getElementById('loading').classList.remove('active');
                this.disabled = false;
                this.textContent = '⬇️ Download';
                
                if (data.success) {
                    document.getElementById('downloadLink').href = '/download-file?url=' + encodeURIComponent(data.video_url);
                    document.getElementById('result').classList.add('active');
                } else {
                    showError('❌ ' + (data.error || 'Failed to fetch video'));
                }
            })
            .catch(error => {
                document.getElementById('loading').classList.remove('active');
                this.disabled = false;
                this.textContent = '⬇️ Download';
                showError('❌ Network error. Please try again.');
                console.error('Error:', error);
            });
        });
        
        function showError(message) {
            const errorDiv = document.getElementById('error');
            errorDiv.textContent = message;
            errorDiv.classList.add('active');
        }
        
        // Enter key support
        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                document.getElementById('downloadBtn').click();
            }
        });
    </script>
</body>
</html>
"""

# ============= FLASK ROUTES =============

@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE)

@app.route('/api/download', methods=['POST'])
def api_download():
    """API endpoint to get video URL from Instagram URL"""
    try:
        data = request.get_json()
        if not data or not data.get('url'):
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        
        insta_url = data['url'].strip()
        
        # Validate Instagram URL
        instagram_pattern = re.compile(r'(?:https?://)?(?:www\.)?instagram\.com/(?:reel|p|tv)/[A-Za-z0-9_-]+')
        if not instagram_pattern.match(insta_url):
            return jsonify({'success': False, 'error': 'Invalid Instagram URL'}), 400
        
        # Get video URL
        video_url = get_instagram_video_url(insta_url)
        
        if video_url:
            return jsonify({
                'success': True,
                'video_url': video_url,
                'original_url': insta_url
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Could not fetch video. Make sure the URL is public.'
            }), 404
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download-file')
def download_file():
    """Download video file"""
    video_url = request.args.get('url', '')
    if not video_url:
        return "❌ No video URL provided!", 400
    
    try:
        video_url = unquote(video_url)
    except:
        pass
    
    try:
        # Download video with streaming
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'video/mp4,video/*;q=0.9,*/*;q=0.8',
        }
        response = requests.get(video_url, headers=headers, stream=True, timeout=120)
        if response.status_code != 200:
            return f"❌ Download failed! Status: {response.status_code}", 400
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        
        # Download in chunks
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    progress = int(downloaded * 100 / total_size)
                    print(f"Download progress: {progress}%")
        
        temp_file.close()
        
        # Send file
        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name='instagram_video.mp4',
            mimetype='video/mp4'
        )
        
    except Exception as e:
        return f"❌ Error: {str(e)}", 500

# ============= MAIN =============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🚀 Instagram Downloader Server Started!")
    print(f"🌐 Running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
