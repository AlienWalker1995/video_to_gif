import json
import subprocess
import tempfile
import os
from flask import Flask, render_template, request, send_file, jsonify
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB


PRESETS = {
    'embed': {'max_size': 240, 'fps': 10, 'colors': 64},   # Smallest — docs, Slack, email
    'web':   {'max_size': 360, 'fps': 15, 'colors': 128},  # Balanced — web embedding
    'full':  {'max_size': 480, 'fps': 15, 'colors': 256},  # Best quality
}


def probe_video(path):
    result = subprocess.run([
        'ffprobe', '-v', 'quiet', '-print_format', 'json',
        '-show_streams', '-show_format', path
    ], capture_output=True, check=True)
    info = json.loads(result.stdout)
    video_stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    width = int(video_stream['width'])
    height = int(video_stream['height'])
    duration = float(info.get('format', {}).get('duration') or video_stream.get('duration') or 0)
    return width, height, duration


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert():
    preset_name = request.form.get('preset', 'full').lower()
    preset = PRESETS.get(preset_name, PRESETS['full'])
    max_size = preset['max_size']
    fps = preset['fps']
    colors = preset['colors']

    try:
        speed = max(1, int(request.form.get('speed', 1)))
    except ValueError:
        speed = 1

    # Resolve input: URL takes priority over file upload
    url = request.form.get('url', '').strip()
    if url:
        if not url.startswith(('http://', 'https://')):
            return jsonify({'error': 'URL must begin with http:// or https://'}), 400
        input_source = url
        save_file = None
    elif 'video' in request.files and request.files['video'].filename:
        save_file = request.files['video']
        input_source = None  # set after saving
    else:
        return jsonify({'error': 'Provide a video file or a URL'}), 400

    with tempfile.TemporaryDirectory() as tmpdir:
        palette_path = os.path.join(tmpdir, 'palette.png')
        output_path  = os.path.join(tmpdir, 'output.gif')

        if save_file is not None:
            filename = secure_filename(save_file.filename) or 'upload'
            input_source = os.path.join(tmpdir, filename)
            save_file.save(input_source)

        # Validate via ffprobe and read dimensions + duration
        try:
            width, height, duration = probe_video(input_source)
        except subprocess.CalledProcessError:
            return jsonify({'error': 'Not a valid video, format unsupported, or URL unreachable'}), 400
        except StopIteration:
            return jsonify({'error': 'No video stream found'}), 400

        # Aspect-ratio-aware scaling
        scale_filter = f'-1:{max_size}' if height > width else f'{max_size}:-1'

        # Speed filter: compress timestamps so GIF plays faster
        speed_filter = f'setpts=PTS/{speed},' if speed > 1 else ''

        # Pass 1: palette generation
        try:
            subprocess.run([
                'ffmpeg', '-i', input_source,
                '-vf', f'{speed_filter}fps={fps},scale={scale_filter}:flags=lanczos,palettegen=stats_mode=diff:max_colors={colors}',
                '-y', palette_path
            ], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            return jsonify({'error': f'Palette generation failed: {e.stderr.decode()}'}), 500

        # Pass 2: GIF encode
        try:
            subprocess.run([
                'ffmpeg', '-i', input_source, '-i', palette_path,
                '-lavfi', f'{speed_filter}fps={fps},scale={scale_filter}:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle',
                '-y', output_path
            ], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            return jsonify({'error': f'GIF encoding failed: {e.stderr.decode()}'}), 500

        response = send_file(output_path, mimetype='image/gif', as_attachment=True, download_name='output.gif')
        response.headers['X-Video-Duration'] = f'{duration:.2f}'
        response.headers['X-Video-Speed'] = str(speed)
        return response


if __name__ == '__main__':
    app.run(port=3000, debug=True)
