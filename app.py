import os
import re
import requests
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

PIPED_INSTANCES = [
    'https://pipedapi.kavin.rocks',
    'https://pipedapi.adminforge.de',
    'https://pipedapi.darkness.services',
    'https://api.piped.projectsegfau.lt',
]

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
    seconds = int(seconds)
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f'{hours}:{mins:02d}:{secs:02d}'
    return f'{mins}:{secs:02d}'


def get_ytdlp_info(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
            'skip_download': True,
            'geo_bypass': True,
            'socket_timeout': 30,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'tv'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print('[OK] yt-dlp success')
        return info
    except Exception as e:
        print(f'[WARN] yt-dlp failed: {e}')
        return None


def get_ytdlp_download_url(url, fmt, quality):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'no_check_certificate': True,
            'geo_bypass': True,
            'socket_timeout': 30,
            'extractor_args': {
                'youtube': {
                    'player_client': ['mweb', 'tv'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
            },
        }
        if fmt == 'mp3':
            ydl_opts['format'] = 'bestaudio/best'
        else:
            height_match = re.search(r'(\d+)', quality)
            height = int(height_match.group(1)) if height_match else 720
            # Prefer muxed formats (video+audio together), fallback to best available
            ydl_opts['format'] = f'best[height<={height}][ext=mp4]/best[height<={height}]/bestvideo[height<={height}]+bestaudio/best[height<={height}]/best'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        download_url = info.get('url', '')
        if not download_url:
            # For muxed formats, requested_formats has both video and audio
            if 'requested_formats' in info:
                # Return the video stream URL (audio is separate for high quality)
                download_url = info['requested_formats'][0].get('url', '')
            elif 'formats' in info and info['formats']:
                # Get the last format (usually best quality)
                for f in reversed(info['formats']):
                    if f.get('url'):
                        download_url = f['url']
                        break

        if download_url:
            print('[OK] yt-dlp download URL obtained')
        return download_url
    except Exception as e:
        print(f'[WARN] yt-dlp download failed: {e}')
        return ''


def get_piped_info(video_id):
    for instance in PIPED_INSTANCES:
        try:
            url = f'{instance}/streams/{video_id}'
            resp = requests.get(url, timeout=15, headers=HEADERS)
            if resp.status_code == 200:
                data = resp.json()
                # Check for error in response
                if data.get('error'):
                    print(f'[WARN] Piped {instance}: {data["error"]}')
                    continue
                if data.get('title'):
                    print(f'[OK] Piped: {instance}')
                    return data
        except Exception as e:
            print(f'[WARN] Piped {instance}: {e}')
    return None


def get_oembed_info(video_id):
    try:
        url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
        resp = requests.get(url, timeout=10, headers=HEADERS)
        if resp.status_code == 200:
            data = resp.json()
            print('[OK] oEmbed success')
            return {
                'title': data.get('title', 'Untitled'),
                'channel': data.get('author_name', 'Unknown'),
                'thumbnail': data.get('thumbnail_url', f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'),
            }
    except Exception as e:
        print(f'[WARN] oEmbed: {e}')
    return None


def build_piped_formats(info):
    formats = []
    seen = set()

    # Video streams
    for f in info.get('videoStreams', []):
        if f.get('audioOnly', False):
            continue
        quality = f.get('quality', 'unknown')
        vonly = f.get('videoOnly', False)
        label = f'{quality} (video only)' if vonly else quality
        key = f'{quality}_{vonly}'
        if key in seen:
            continue
        seen.add(key)
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': 'mp4',
            'quality': label,
            'filesize': format_filesize(f.get('contentLength')),
            'has_audio': not vonly,
            'has_video': True,
        })

    # Audio streams
    for f in info.get('audioStreams', []):
        bitrate = f.get('bitrate', 0)
        quality = f'{bitrate // 1000}kbps audio' if bitrate else 'audio'
        key = f'audio_{bitrate}'
        if key in seen:
            continue
        seen.add(key)
        formats.append({
            'format_id': f.get('itag', ''),
            'ext': 'mp4',
            'quality': quality,
            'filesize': format_filesize(f.get('contentLength')),
            'has_audio': True,
            'has_video': False,
        })

    return formats


def build_ytdlp_formats(info):
    formats = []
    seen = set()
    for f in info.get('formats', []):
        if not f.get('url'):
            continue
        quality = f.get('quality_label') or f.get('format_note') or 'unknown'
        ext = f.get('ext', 'mp4')
        has_audio = f.get('acodec') != 'none'
        has_video = f.get('vcodec') != 'none'

        # Skip format-only streams that have neither audio nor video
        if not has_audio and not has_video:
            continue

        key = f'{quality}_{ext}_{has_audio}_{has_video}'
        if key in seen:
            continue
        seen.add(key)

        filesize = f.get('filesize') or f.get('filesize_approx')
        formats.append({
            'format_id': f.get('format_id', ''),
            'ext': ext,
            'quality': quality,
            'filesize': format_filesize(filesize),
            'has_audio': has_audio,
            'has_video': has_video,
        })

    return formats


def format_filesize(size_bytes):
    """Format bytes to human readable size."""
    if not size_bytes:
        return 'N/A'
    try:
        size_bytes = int(size_bytes)
    except (ValueError, TypeError):
        return 'N/A'
    if size_bytes <= 0:
        return 'N/A'
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f'{mb / 1024:.1f} GB'
    if mb >= 1:
        return f'{mb:.0f} MB'
    kb = size_bytes / 1024
    return f'{kb:.0f} KB'


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
        if not data:
            return jsonify({'success': False, 'error': 'Invalid request body'}), 400

        url = data.get('url', '').strip()
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'}), 400
        if not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'Invalid YouTube URL'}), 400

        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({'success': False, 'error': 'Could not extract video ID'}), 400

        # Method 1: yt-dlp
        ytdlp = get_ytdlp_info(url)
        if ytdlp:
            thumb = ytdlp.get('thumbnail', '')
            if not thumb:
                thumb = f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
            return jsonify({
                'success': True,
                'data': {
                    'id': video_id,
                    'title': ytdlp.get('title', 'Untitled'),
                    'channel': ytdlp.get('channel') or ytdlp.get('uploader') or 'Unknown',
                    'views': format_views(ytdlp.get('view_count')),
                    'duration': format_duration(ytdlp.get('duration')),
                    'thumbnail': thumb,
                    'formats': build_ytdlp_formats(ytdlp),
                }
            })

        # Method 2: Piped
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
                }
            })

        # Method 3: oEmbed (limited info, no formats)
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
                }
            })

        return jsonify({
            'success': False,
            'error': 'All servers busy. Please try again later.'
        }), 503

    except Exception as e:
        print(f'[ERROR] /api/info: {e}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Invalid request body'}), 400

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

        if fmt not in ('mp4', 'mp3'):
            return jsonify({'success': False, 'error': 'Invalid format. Use mp4 or mp3'}), 400

        title = 'download'

        # Method 1: yt-dlp
        download_url = get_ytdlp_download_url(url, fmt, quality)
        if download_url:
            return jsonify({
                'success': True,
                'data': {
                    'downloadUrl': download_url,
                    'title': title,
                    'ext': 'mp3' if fmt == 'mp3' else 'mp4',
                }
            })

        # Method 2: Piped
        piped = get_piped_info(video_id)
        if piped:
            title = piped.get('title', 'download')
            download_url = ''

            if fmt == 'mp3':
                # Get highest bitrate audio
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
                # Match requested quality
                height_match = re.search(r'(\d+)', quality)
                target = int(height_match.group(1)) if height_match else 720

                # Get video+audio combined streams first
                combined = [f for f in piped.get('videoStreams', [])
                           if not f.get('videoOnly', True)]
                if combined:
                    # Find best match
                    for f in combined:
                        h = re.search(r'(\d+)', f.get('quality', ''))
                        if h and int(h.group(1)) <= target:
                            download_url = f.get('url', '')
                            break

                # Fallback to video-only streams
                if not download_url:
                    streams = [f for f in piped.get('videoStreams', [])
                              if not f.get('audioOnly', False)]
                    # Try exact match
                    for f in streams:
                        h = re.search(r'(\d+)', f.get('quality', ''))
                        if h and int(h.group(1)) == target:
                            download_url = f.get('url', '')
                            break
                    # Try closest lower
                    if not download_url:
                        best_lower = None
                        best_h = 0
                        for f in streams:
                            h = re.search(r'(\d+)', f.get('quality', ''))
                            if h:
                                hv = int(h.group(1))
                                if hv <= target and hv > best_h:
                                    best_h = hv
                                    best_lower = f
                        if best_lower:
                            download_url = best_lower.get('url', '')
                    # Last resort: any stream
                    if not download_url and streams:
                        download_url = streams[-1].get('url', '')

            if download_url:
                return jsonify({
                    'success': True,
                    'data': {
                        'downloadUrl': download_url,
                        'title': title,
                        'ext': 'mp3' if fmt == 'mp3' else 'mp4',
                    }
                })

        # Method 3: Final fallback - construct a search-based redirect
        return jsonify({
            'success': False,
            'error': 'Could not generate download link. The video may be restricted or servers are busy. Please try again.'
        }), 503

    except Exception as e:
        print(f'[ERROR] /api/download: {e}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.route('/api/contact', methods=['POST'])
def api_contact():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Invalid request body'}), 400

        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message = data.get('message', '').strip()

        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Valid email is required'}), 400
        if not message:
            return jsonify({'success': False, 'error': 'Message is required'}), 400

        # In production, you'd send an email or save to database here
        # For now, just log and return success
        print(f'[CONTACT] Name: {name}, Email: {email}, Message: {message[:100]}...')

        return jsonify({
            'success': True,
            'message': 'Thank you! Your message has been received.'
        })

    except Exception as e:
        print(f'[ERROR] /api/contact: {e}')
        return jsonify({'success': False, 'error': 'Internal server error'}), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({'success': False, 'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500


if __name__ == '__main__':
    print('\n  GrabTube Server Starting...')
    print('  Open http://localhost:5000 in your browser\n')
    app.run(debug=True, host='0.0.0.0', port=5000)
