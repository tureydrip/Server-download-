import os
import time
import tempfile
import shutil
import requests
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
# Habilitar CORS para permitir peticiones desde tu frontend
CORS(app)

# Configuración de directorios temporales
TEMP_DIR = tempfile.gettempdir()
DOWNLOAD_DIR = os.path.join(TEMP_DIR, 'luck_xit_downloads')
MEDIA_DIR = os.path.join(DOWNLOAD_DIR, 'media')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# API de TIKWM para TikTok
TIKWM_API = "https://www.tikwm.com/api/"

def is_tiktok_url(url):
    return 'tiktok.com' in url.lower() or 'vm.tiktok.com' in url.lower()

def get_tiktok_info(url):
    try:
        response = requests.post(TIKWM_API, data={'url': url, 'hd': 1}, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0:
                return data.get('data')
        return None
    except Exception as e:
        print(f"Error en TIKWM API: {e}")
        return None

def cleanup_old_files():
    """Elimina archivos con más de 1 hora de antigüedad para evitar que Railway se llene"""
    current_time = time.time()
    for directory in [DOWNLOAD_DIR, MEDIA_DIR]:
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            try:
                if os.path.isfile(filepath) and os.stat(filepath).st_mtime < current_time - 3600:
                    os.remove(filepath)
            except Exception as e:
                print(f"Error limpiando {filepath}: {e}")

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'LUCK XIT Server Running'})

@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(MEDIA_DIR, filename)

@app.route('/preview', methods=['POST'])
def preview():
    cleanup_old_files()
    try:
        url = request.form.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL no proporcionada'}), 400

        timestamp = int(time.time() * 1000)

        # ============ TIKTOK CON TIKWM API ============
        if is_tiktok_url(url):
            tiktok_data = get_tiktok_info(url)
            if not tiktok_data:
                return jsonify({'error': 'No se pudo obtener información de TikTok'}), 500
            
            images = tiktok_data.get('images', [])
            if images:
                return jsonify({
                    'success': True,
                    'type': 'gallery',
                    'platform': 'tiktok',
                    'images': images,
                    'title': tiktok_data.get('title', 'Galería de TikTok'),
                    'thumbnail': images[0] if images else None,
                    'uploader': tiktok_data.get('author', {}).get('unique_id', 'Desconocido'),
                })
            else:
                video_url = tiktok_data.get('hdplay') or tiktok_data.get('play')
                cover = tiktok_data.get('cover')
                return jsonify({
                    'success': True,
                    'type': 'video',
                    'platform': 'tiktok',
                    'title': tiktok_data.get('title', 'Video de TikTok'),
                    'thumbnail': cover,
                    'video_url': video_url, # Directo de la API para vista previa
                    'audio_url': tiktok_data.get('music_info', {}).get('play'),
                    'uploader': tiktok_data.get('author', {}).get('unique_id', 'Desconocido'),
                })

        # ============ OTRAS PLATAFORMAS CON YT-DLP ============
        ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumbnails = info.get('thumbnails', [])
            thumbnail = thumbnails[-1]['url'] if thumbnails else info.get('thumbnail')

            return jsonify({
                'success': True,
                'type': 'video',
                'platform': 'other',
                'title': info.get('title', 'Sin título'),
                'thumbnail': thumbnail,
                'uploader': info.get('uploader', 'Desconocido'),
            })

    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download():
    cleanup_old_files()
    try:
        url = request.form.get('url', '').strip()
        kind = request.form.get('kind', 'video')

        if not url:
            return jsonify({'error': 'URL no proporcionada'}), 400

        timestamp = int(time.time() * 1000)

        # ============ TIKTOK CON TIKWM API ============
        if is_tiktok_url(url):
            tiktok_data = get_tiktok_info(url)
            if not tiktok_data:
                return jsonify({'error': 'No se pudo obtener información de TikTok'}), 500
            
            if kind == 'gallery':
                images = tiktok_data.get('images', [])
                if not images:
                    return jsonify({'error': 'No se encontraron imágenes'}), 404
                
                import zipfile
                zip_filename = f'luck_xit_gallery_{timestamp}.zip'
                zip_path = os.path.join(DOWNLOAD_DIR, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for idx, img_url in enumerate(images, 1):
                        img_response = requests.get(img_url, timeout=30)
                        if img_response.status_code == 200:
                            zipf.writestr(f'imagen_{idx:03d}.jpg', img_response.content)
                
                return send_file(zip_path, mimetype='application/zip', as_attachment=True, download_name=zip_filename)
            
            elif kind == 'video':
                video_url = tiktok_data.get('hdplay') or tiktok_data.get('play')
                video_filename = f'luck_xit_video_{timestamp}.mp4'
                video_path = os.path.join(DOWNLOAD_DIR, video_filename)
                
                video_response = requests.get(video_url, timeout=120, stream=True)
                with open(video_path, 'wb') as f:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return send_file(video_path, mimetype='video/mp4', as_attachment=True, download_name=video_filename)
            
            elif kind == 'audio':
                music_url = tiktok_data.get('music_info', {}).get('play')
                audio_filename = f'luck_xit_audio_{timestamp}.mp3'
                audio_path = os.path.join(DOWNLOAD_DIR, audio_filename)
                
                audio_response = requests.get(music_url, timeout=60)
                with open(audio_path, 'wb') as f:
                    f.write(audio_response.content)
                return send_file(audio_path, mimetype='audio/mpeg', as_attachment=True, download_name=audio_filename)

        # ============ OTRAS PLATAFORMAS CON YT-DLP ============
        output_template = os.path.join(DOWNLOAD_DIR, f'luck_xit_{timestamp}.%(ext)s')

        if kind == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                'quiet': True, 'no_warnings': True,
            }
            file_extension = 'mp3'
            mimetype = 'audio/mpeg'
        else:
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': output_template,
                'quiet': True, 'no_warnings': True,
                'merge_output_format': 'mp4',
            }
            file_extension = 'mp4'
            mimetype = 'video/mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        downloaded_file = None
        for file in os.listdir(DOWNLOAD_DIR):
            if file.startswith(f'luck_xit_{timestamp}') and file.endswith(f'.{file_extension}'):
                downloaded_file = os.path.join(DOWNLOAD_DIR, file)
                break

        if not downloaded_file:
            return jsonify({'error': 'Error al descargar el archivo'}), 500

        return send_file(downloaded_file, mimetype=mimetype, as_attachment=True, download_name=f'luck_xit_{kind}_{timestamp}.{file_extension}')

    except Exception as e:
        return jsonify({'error': f'Error en la descarga: {str(e)}'}), 500

if __name__ == '__main__':
    # Puerto dinámico para Railway
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
