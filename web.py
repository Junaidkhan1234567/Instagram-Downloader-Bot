from flask import Flask, request, send_file, render_template_string
import requests
import os
import tempfile
from urllib.parse import unquote

app = Flask(__name__)

# HTML Template for download page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Instagram Video Downloader</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
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
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            width: 100%;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: slideUp 0.5s ease;
        }
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .icon {
            font-size: 60px;
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 16px;
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
        .btn {
            display: inline-block;
            padding: 15px 40px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: bold;
            font-size: 18px;
            transition: all 0.3s;
            margin: 15px 0;
            border: none;
            cursor: pointer;
        }
        .btn:hover {
            background: #218838;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40,167,69,0.3);
        }
        .error {
            color: #dc3545;
            background: #f8d7da;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        .success {
            color: #28a745;
            margin: 15px 0;
        }
        .hidden {
            display: none;
        }
        .footer {
            margin-top: 20px;
            color: #999;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📥</div>
        <h1>Instagram Downloader</h1>
        <p class="subtitle">आपका वीडियो तैयार है!</p>
        
        <div id="loading">
            <div class="spinner"></div>
            <p>⏳ <b>डाउनलोड शुरू हो रहा है...</b></p>
            <p style="color: #666; font-size: 14px; margin-top: 10px;">
                कृपया कुछ सेकंड इंतज़ार करें
            </p>
        </div>
        
        <div id="result" class="hidden">
            <div class="success">✅ <b>वीडियो डाउनलोड हो रहा है</b></div>
            <a href="#" id="downloadBtn" class="btn">⬇️ फिर से डाउनलोड करें</a>
            <p style="color: #666; font-size: 14px; margin-top: 10px;">
                अगर डाउनलोड शुरू नहीं होता, तो ऊपर बटन पर क्लिक करें
            </p>
        </div>
        
        <div id="error" class="hidden error"></div>
        
        <div class="footer">
            🔒 सुरक्षित डाउनलोड | ⚡ तेज़
        </div>
    </div>
    
    <script>
        window.onload = function() {
            const urlParams = new URLSearchParams(window.location.search);
            const videoUrl = urlParams.get('url');
            
            if (!videoUrl) {
                showError('❌ Video URL नहीं मिला! कृपया सही लिंक का उपयोग करें।');
                return;
            }
            
            setTimeout(function() {
                const downloadUrl = '/download-file?url=' + encodeURIComponent(videoUrl);
                window.location.href = downloadUrl;
                
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('result').classList.remove('hidden');
                document.getElementById('downloadBtn').href = downloadUrl;
            }, 2000);
        };
        
        function showError(msg) {
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('result').classList.add('hidden');
            document.getElementById('error').classList.remove('hidden');
            document.getElementById('error').textContent = msg;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Instagram Downloader API</title>
        <style>
            body {
                font-family: Arial, sans-serif;
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
                border-radius: 20px;
                padding: 40px;
                max-width: 500px;
                width: 100%;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 { color: #333; }
            .status { color: #28a745; font-size: 18px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📸 Instagram Video Downloader</h1>
            <p class="status">✅ API is running!</p>
            <p>Telegram Bot से लिंक जनरेट करें</p>
            <p style="color: #666; font-size: 14px;">🔗 /download?url=VIDEO_URL</p>
        </div>
    </body>
    </html>
    """

@app.route('/download')
def download_page():
    """Download page with auto download"""
    video_url = request.args.get('url', '')
    if not video_url:
        return "❌ No video URL provided!", 400
    
    try:
        video_url = unquote(video_url)
    except:
        pass
    
    return render_template_string(HTML_TEMPLATE)

@app.route('/download-file')
def download_file():
    """Direct file download"""
    video_url = request.args.get('url', '')
    if not video_url:
        return "❌ No video URL provided!", 400
    
    try:
        video_url = unquote(video_url)
    except:
        pass
    
    try:
        # Download video with streaming
        response = requests.get(video_url, stream=True, timeout=120)
        if response.status_code != 200:
            return f"❌ Download failed! Status: {response.status_code}", 400
        
        # Create temp file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        
        # Download in chunks
        downloaded = 0
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                temp_file.write(chunk)
                downloaded += len(chunk)
        
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
