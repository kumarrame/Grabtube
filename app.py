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

PIPED_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.adminforge.de',
    'https://pipedapi.darkness.services',
    'https://api.piped.projectsegfau.lt',
    'https://piped-api.lunar.icu',
]

INVIDIOUS_INSTANCES = [
    'https://inv.nadeko.net',
    'https://invidious.nerdvpn.de',
    'https://invidious.perennialte.ch',
    'https://vid.puffyan.us',
    'https://yewtu.be',
]

COBALT_API = 'https://api.cobalt.tools'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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


# ──────────────────────────────
# API 1: YouTube oEmbed (always works for basic info)
# ──────────────────────────────
def get_oembed_info(video_id):
    try:
        url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'title': data.get('title', 'Untitled'),
                'channel': data.get('author_name', 'Unknown'),
                'thumbnail': data.get('thumbnail_url', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
            }
    except Exception as e:
        print(f'[WARN] oEmbed failed: {e}')
    return None


# ──────────────────────────────
# API 2: Piped API (full info + streams)
# ──────────────────────────────
def get_piped_info(video_id):
    for instance in PIPED_INSTANCES:
        try:
            url = f'{instance}/streams/{video_id}'
            resp = requests.get(url, timeout=15, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('title'):
                    print(f'[OK] Piped: {instance}')
                    return data
        except Exception as e:
            print(f'[WARN] Piped {instance}: {e}')
            continue
    return None


# ──────────────────────────────
# API 3: Invidious API (fallback for info)
# ──────────────────────────────
def get_invidious_info(video_id):
    for instance in INVIDIOUS_INSTANCES:
        try:
            url = f'{instance}/api/v1/videos/{video_id}'
            resp = requests.get(url, timeout=15, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('title'):
                    print(f'[OK] Invidious: {instance}')
                    return data
        except Exception as e:
            print(f'[WARN] Invidious {instance}: {e}')
            continue
    return None


# ──────────────────────────────
# API 4: Cobalt API (reliable download links)
# ──────────────────────────────
def get_cobalt_download(video_url, audio_only=False):
    try:
        payload = {
            'url': video_url,
            'downloadMode': 'audio' if audio_only else 'auto',
            'filenameStyle': 'basic',
        }
        resp = requests.post(
            COBALT_API,
            json=payload,
            headers={
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('url'):
                print(f'[OK] Cobalt download link obtained')
                return data['url']
            if data.get('status') == 'error':
                print(f'[WARN] Cobalt error: {data.get("error", "unknown")}')
    except Exception as e:
        print(f'[WARN] Cobalt failed: {e}')
    return None


# ──────────────────────────────
# Build formats from Piped data
# ──────────────────────────────
def build_piped_formats(info):
    formats = []
    seen = set()

    for f in info.get('videoStreams', []):
        if f.get('audioOnly', False):
            continue
        quality = f.get('quality', 'unknown')
        ext = f.get('mimeType', 'video/mp4').split('/')[-1]
        video_only = f.get('videoOnly', False)
        key = f'{quality}_{ext}_{video_only}'
        if key in seen:
            continue
        seen.add(key)
        bitrate = f.get('bitrate', 0)
        size_mb = round(bitrate * info.get('duration', 0) / 8 / 1024 / 1024) if bitrate else 0
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': ext,
            'quality': quality,
            'filesize': f'{size_mb} MB' if size_mb else 'N/A',
            'has_audio': not video_only,
            'has_video': True,
        })

    for f in info.get('audioStreams', []):
        bitrate = f.get('bitrate', 0)
        quality = f'{bitrate // 1000}kbps' if bitrate else 'audio'
        ext = f.get('mimeType', 'audio/mp4').split('/')[-1]
        key = f'audio_{bitrate}'
        if key in seen:
            continue
        seen.add(key)
        size_mb = round(bitrate * info.get('duration', 0) / 8 / 1024 / 1024) if bitrate else 0
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': ext,
            'quality': quality,
            'filesize': f'{size_mb} MB' if size_mb else 'N/A',
            'has_audio': True,
            'has_video': False,
        })

    return formats


# ──────────────────────────────
# Build formats from Invidious data
# ──────────────────────────────
def build_invidious_formats(info):
    formats = []
    seen = set()

    for f in info.get('formatStreams', []):
        quality = f.get('qualityLabel') or f.get('quality', 'unknown')
        ext = f.get('container', 'mp4')
        key = f'{quality}_{ext}'
        if key in seen:
            continue
        seen.add(key)
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': ext,
            'quality': quality,
            'filesize': 'N/A',
            'has_audio': True,
            'has_video': True,
        })

    for f in info.get('adaptiveFormats', []):
        quality = f.get('qualityLabel') or f.get('quality', 'unknown')
        codec = f.get('type', '')
        ext = f.get('container', 'mp4')
        if 'audio' in codec:
            br = f.get('bitrate', 0)
            quality = f'{br // 1000}kbps' if br else 'audio'
            key = f'audio_{br}'
        else:
            key = f'{quality}_{ext}'
        if key in seen:
            continue
        seen.add(key)
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': ext,
            'quality': quality,
            'filesize': 'N/A',
            'has_audio': 'audio' in codec,
            'has_video': 'video' in codec,
        })

    return formats


# ──────────────────────────────
# Pages
# ──────────────────────────────
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


# ──────────────────────────────
# API: Get Video Info
# ──────────────────────────────
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

        # Try Piped first (has full info)
        piped = get_piped_info(video_id)
        if piped:
            thumb = piped.get('thumbnailUrl', '')
            if not thumb:
                thumb = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            return jsonify({
                'success': True,
                'data': {
                    'id': video_id,
                    'title': piped.get('title', 'Untitled'),
                    'channel': piped.get('uploader', 'Unknown'),
                    'views': format_views(piped.get('views')),
                    'duration': format_duration(piped.get('duration')),
                    'thumbnail': thumb,
                    'formats': build_piped_formats(piped),
                    'api_source': 'piped',
                }
            })

        # Try Invidious
        invidious = get_invidious_info(video_id)
        if invidious:
            thumb = ''
            if invidious.get('videoThumbnails'):
                thumb = invidious['videoThumbnails'][0].get('url', '')
            if not thumb:
                thumb = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            return jsonify({
                'success': True,
                'data': {
                    'id': video_id,
                    'title': invidious.get('title', 'Untitled'),
                    'channel': invidious.get('author', 'Unknown'),
                    'views': format_views(invidious.get('viewCount')),
                    'duration': format_duration(invidious.get('lengthSeconds')),
                    'thumbnail': thumb,
                    'formats': build_invidious_formats(invidious),
                    'api_source': 'invidious',
                }
            })

        # Fallback: YouTube oEmbed (basic info only)
        oembed = get_oembed_info(video_id)
        if oembed:
            return jsonify({
                'success': True,
                'data': {
                    'id': video_id,
                    'title': oembed['title'],
                    'channel': oembed['channel'],
                    'views': 'N/A',
                    'duration': 'N/A',
                    'thumbnail': oembed['thumbnail'],
                    'formats': [],
                    'api_source': 'oembed',
                }
            })

        return jsonify({
            'success': False,
            'error': 'All servers busy. Please try again in a minute.'
        }), 500

    except Exception as e:
        print(f'[ERROR] /api/info: {e}')
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500


# ──────────────────────────────
# API: Get Download Link
# ──────────────────────────────
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

        download_url = ''
        title = 'download'

        # Try Piped
        piped = get_piped_info(video_id)
        if piped:
            title = piped.get('title', 'download')

            if fmt == 'mp3':
                # Best audio stream
                best = None
                best_br = 0
                for f in piped.get('audioStreams', []):
                    br = f.get('bitrate', 0)
                    if br > best_br:
                        best_br = br
                        best = f
                if best:
                    download_url = best.get('url', '')
            else:
                # Find video matching quality
                height_match = re.search(r'(\d+)', quality)
                target = int(height_match.group(1)) if height_match else 720

                # Any video stream (videoOnly OK too)
                all_videos = piped.get('videoStreams', [])
                for f in all_videos:
                    h = re.search(r'(\d+)', f.get('quality', ''))
                    if h and int(h.group(1)) == target:
                        download_url = f.get('url', '')
                        break

                # Lower quality fallback
                if not download_url:
                    for f in all_videos:
                        h = re.search(r'(\d+)', f.get('quality', ''))
                        if h and int(h.group(1)) <= target:
                            download_url = f.get('url', '')
                            break

                # Any stream fallback
                if not download_url and all_videos:
                    download_url = all_videos[0].get('url', '')

        # Try Invidious fallback
        if not download_url:
            invidious = get_invidious_info(video_id)
            if invidious:
                title = invidious.get('title', 'download')

                if fmt == 'mp3':
                    best = None
                    best_br = 0
                    for f in invidious.get('adaptiveFormats', []):
                        if 'audio' in f.get('type', ''):
                            br = f.get('bitrate', 0)
                            if br > best_br:
                                best_br = br
                                best = f
                    if best:
                        download_url = best.get('url', '')
                else:
                    streams = invidious.get('formatStreams', [])
                    if streams:
                        download_url = streams[-1].get('url', '')

        if not download_url:
            return jsonify({
                'success': False,
                'error': 'Could not get download link. Try again later.'
            }), 500

        return jsonify({
            'success': True,
            'data': {
                'downloadUrl': download_url,
                'title': title,
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