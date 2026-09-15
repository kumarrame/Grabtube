import os
import re
import traceback
import yt_dlp
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-key-change-later')
CORS(app)

YOUTUBE_REGEX = re.compile(
    r'^(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[\w\-]{11}'
)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def is_valid_youtube_url(url):
    return bool(YOUTUBE_REGEX.match(url.strip()))

def extract_video_id(url):
    match = re.search(r'(?:v=|youtu\.be/|shorts/)([\w\-]{11})', url)
    return match.group(1) if match else None

def format_views(count):
    if not count:
        return 'N/A'
    if count >= 1_000_000_000:
        return f'{count / 1_000_000_000:.1f}B views'
    if count >= 1_000_000:
        return f'{count / 1_000_000:.1f}M views'
    if count >= 1_000:
        return f'{count / 1_000:.1f}K views'
    return f'{count} views'

def format_duration(seconds):
    if not seconds:
        return '0:00'
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f'{mins}:{secs:02d}'

def format_filesize(size_bytes):
    if not size_bytes:
        return 'Unknown'
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f'{mb / 1024:.1f} GB'
    return f'{mb:.0f} MB'


@app.route('/')
def home():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/api/info', methods=['POST'])
def api_info():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        if not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
            'skip_download': True,
            'no_color': True,
            'geo_bypass': True,
            'http_headers': HEADERS,
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        video_id = info.get('id', extract_video_id(url))

        formats_list = []
        seen = set()
        for f in info.get('formats', []):
            if not f.get('url'):
                continue
            quality = f.get('quality_label') or f.get('format_note') or 'unknown'
            ext = f.get('ext', 'unknown')
            key = f'{quality}_{ext}'
            if key in seen:
                continue
            seen.add(key)
            formats_list.append({
                'format_id': f.get('format_id'),
                'ext': ext,
                'quality': quality,
                'filesize': format_filesize(f.get('filesize') or f.get('filesize_approx')),
                'has_audio': f.get('acodec') != 'none',
                'has_video': f.get('vcodec') != 'none',
            })

        return jsonify({
            'success': True,
            'data': {
                'id': video_id,
                'title': info.get('title', 'Untitled'),
                'channel': info.get('channel') or info.get('uploader') or 'Unknown',
                'views': format_views(info.get('view_count')),
                'duration': format_duration(info.get('duration')),
                'thumbnail': info.get('thumbnail') or f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                'formats': formats_list,
            }
        })

    except Exception as e:
        print(f'[ERROR] /api/info: {e}')
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Could not fetch video info: {str(e)}'
        }), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        fmt = data.get('format', 'mp4')
        quality = data.get('quality', '720p HD')

        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        if not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'http_headers': HEADERS,
            'socket_timeout': 30,
        }

        if fmt == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
        else:
            height_match = re.search(r'(\d+)', quality)
            height = int(height_match.group(1)) if height_match else 720
            ydl_opts['format'] = (
                f'bestvideo[height<={height}]+bestaudio'
                f'/best[height<={height}]'
                f'/best'
            )

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        download_url = info.get('url', '')

        if not download_url:
            if 'requested_formats' in info:
                download_url = info['requested_formats'][0].get('url', '')
            elif 'formats' in info and info['formats']:
                download_url = info['formats'][-1].get('url', '')

        if not download_url:
            return jsonify({
                'success': False,
                'error': 'Could not generate download link. Try different quality.'
            }), 500

        return jsonify({
            'success': True,
            'data': {
                'downloadUrl': download_url,
                'title': info.get('title', 'download'),
                'ext': 'mp3' if fmt == 'mp3' else 'mp4',
            }
        })

    except Exception as e:
        print(f'[ERROR] /api/download: {e}')
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'Could not generate download: {str(e)}'
        }), 500


if __name__ == '__main__':
    print('\n  GrabTube Server Starting...')
    print('  Open http://localhost:5000 in your browser\n')
    app.run(debug=True, host='0.0.0.0', port=5000)