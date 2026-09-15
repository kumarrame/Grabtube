import os
import re
import requests
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

# Working API instances
API_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.adminforge.de',
    'https://api.piped.projectsegfau.lt',
    'https://piped-api.lunar.icu',
    'https://watchapi.whatever.social',
]


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


def fetch_from_piped(video_id):
    """Try multiple Piped API instances"""
    for instance in API_INSTANCES:
        try:
            url = f'{instance}/streams/{video_id}'
            resp = requests.get(url, timeout=20, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if resp.status_code == 200:
                data = resp.json()
                if data.get('title'):
                    print(f'[OK] Using instance: {instance}')
                    return data
        except Exception as e:
            print(f'[WARN] {instance} failed: {e}')
            continue
    return None


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

        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Could not extract video ID'}), 400

        info = fetch_from_piped(video_id)

        if not info:
            return jsonify({
                'success': False,
                'error': 'Could not fetch video info. Servers busy. Try again.'
            }), 500

        # Build formats list
        formats_list = []
        seen = set()

        for f in info.get('videoStreams', []):
            quality = f.get('quality', 'unknown')
            ext = f.get('mimeType', 'video/mp4').split('/')[-1]
            video_only = f.get('videoOnly', False)
            audio_only = f.get('audioOnly', False)

            if audio_only:
                continue

            key = f'{quality}_{ext}_{video_only}'
            if key in seen:
                continue
            seen.add(key)

            bitrate = f.get('bitrate', 0)
            filesize_mb = round(bitrate * info.get('duration', 0) / 8 / 1024 / 1024) if bitrate else 0

            formats_list.append({
                'format_id': f.get('itag', ''),
                'ext': ext,
                'quality': quality,
                'filesize': f'{filesize_mb} MB' if filesize_mb else 'N/A',
                'has_audio': not video_only,
                'has_video': True,
                'url': f.get('url', ''),
            })

        for f in info.get('audioStreams', []):
            bitrate = f.get('bitrate', 0)
            quality = f'{bitrate // 1000}kbps' if bitrate else 'audio'
            ext = f.get('mimeType', 'audio/mp4').split('/')[-1]

            key = f'audio_{bitrate}'
            if key in seen:
                continue
            seen.add(key)

            filesize_mb = round(bitrate * info.get('duration', 0) / 8 / 1024 / 1024) if bitrate else 0

            formats_list.append({
                'format_id': f.get('itag', ''),
                'ext': ext,
                'quality': quality,
                'filesize': f'{filesize_mb} MB' if filesize_mb else 'N/A',
                'has_audio': True,
                'has_video': False,
                'url': f.get('url', ''),
            })

        # Thumbnail
        thumb = info.get('thumbnailUrl', '')
        if not thumb:
            thumb = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'

        return jsonify({
            'success': True,
            'data': {
                'id': video_id,
                'title': info.get('title', 'Untitled'),
                'channel': info.get('uploader', 'Unknown'),
                'views': format_views(info.get('views')),
                'duration': format_duration(info.get('duration')),
                'thumbnail': thumb,
                'formats': formats_list,
            }
        })

    except Exception as e:
        print(f'[ERROR] /api/info: {e}')
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
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

        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Could not extract video ID'}), 400

        info = fetch_from_piped(video_id)

        if not info:
            return jsonify({
                'success': False,
                'error': 'Could not get download link. Try again.'
            }), 500

        download_url = ''

        if fmt == 'mp3':
            # Find best audio stream
            best_audio = None
            best_bitrate = 0
            for f in info.get('audioStreams', []):
                br = f.get('bitrate', 0)
                if br > best_bitrate:
                    best_bitrate = br
                    best_audio = f
            if best_audio:
                download_url = best_audio.get('url', '')
        else:
            # Find video matching quality
            height_match = re.search(r'(\d+)', quality)
            target_height = int(height_match.group(1)) if height_match else 720

            # First try: video with audio (not videoOnly)
            for f in info.get('videoStreams', []):
                if f.get('videoOnly', False):
                    continue
                label = f.get('quality', '')
                h = re.search(r'(\d+)', label)
                if h and int(h.group(1)) == target_height:
                    download_url = f.get('url', '')
                    break

            # Second try: any video stream
            if not download_url:
                for f in info.get('videoStreams', []):
                    label = f.get('quality', '')
                    h = re.search(r'(\d+)', label)
                    if h and int(h.group(1)) <= target_height:
                        download_url = f.get('url', '')
                        break

            # Fallback: first available stream
            if not download_url and info.get('videoStreams'):
                download_url = info['videoStreams'][0].get('url', '')

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
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


if __name__ == '__main__':
    print('\n  GrabTube Server Starting...')
    print('  Open http://localhost:5000 in your browser\n')
    app.run(debug=True, host='0.0.0.0', port=5000)