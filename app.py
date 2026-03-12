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
    if 'video' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['video']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    filename = secure_filename(file.filename) or 'upload'

    preset_name = request.form.get('preset', 'full').lower()
    preset = PRESETS.get(preset_name, PRESETS['full'])
    max_size = preset['max_size']
    fps = preset['fps']
    colors = preset['colors']

    try:
        speed = max(1, int(request.form.get('speed', 1)))
    except ValueError:
        speed = 1

    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, filename)
        palette_path = os.path.join(tmpdir, 'palette.png')
        output_path = os.path.join(tmpdir, 'output.gif')

        file.save(input_path)

        # Validate via ffprobe and get dimensions + duration
        try:
            width, height, duration = probe_video(input_path)
        except subprocess.CalledProcessError:
            return jsonify({'error': 'File is not a valid video or format is unsupported'}), 400
        except StopIteration:
            return jsonify({'error': 'No video stream found in file'}), 400

        # Aspect-ratio-aware scaling
        if height > width:
            scale_filter = f'-1:{max_size}'
        else:
            scale_filter = f'{max_size}:-1'

        # Speed filter: setpts shrinks timestamps, fps keeps output cadence stable
        speed_filter = f'setpts=PTS/{speed},' if speed > 1 else ''

        # Pass 1: palette generation
        try:
            subprocess.run([
                'ffmpeg', '-i', input_path,
                '-vf', f'{speed_filter}fps={fps},scale={scale_filter}:flags=lanczos,palettegen=stats_mode=diff:max_colors={colors}',
                '-y', palette_path
            ], capture_output=True, check=True)
        except subprocess.CalledProcessError as e:
            return jsonify({'error': f'Palette generation failed: {e.stderr.decode()}'}), 500

        # Pass 2: GIF encode
        try:
            subprocess.run([
                'ffmpeg', '-i', input_path, '-i', palette_path,
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
