from flask import Flask, Response, request, jsonify
import os
import threading
import json
import math
import time

app = Flask(__name__)

# Store latest frame and coordinates (thread-safe)
latest_frame = None
frame_lock = threading.Lock()
camera_coords = None  # [X, Y]
coords_lock = threading.Lock()
outage_points = []  # [[x, y], ...]

# Camera parameters
ALTITUDE = 40.0  # meters
HFOV_DEG = 95.0  # horizontal FOV in degrees
VFOV_DEG = 75.0  # vertical FOV in degrees
CANVAS_WIDTH = 640  # pixels
CANVAS_HEIGHT = 480  # pixels

def pixel_to_global(x_pixel, y_pixel):
    """Convert pixel coordinates to global coordinates"""
    with coords_lock:
        if camera_coords is None:
            return None  # No coordinates available

        # Camera global position
        camera_x, camera_y = camera_coords

        # Convert FOV to radians
        hfov_rad = math.radians(HFOV_DEG)
        vfov_rad = math.radians(VFOV_DEG)

        # Ground coverage (meters) at altitude
        ground_width = 2 * ALTITUDE * math.tan(hfov_rad / 2)
        ground_height = 2 * ALTITUDE * math.tan(vfov_rad / 2)

        # Pixel to ground coordinates (relative to image center)
        x_rel = ((x_pixel - CANVAS_WIDTH / 2) / CANVAS_WIDTH) * ground_width
        y_rel = ((CANVAS_HEIGHT / 2 - y_pixel) / CANVAS_HEIGHT) * ground_height

        # Global coordinates
        global_x = camera_x + x_rel
        global_y = camera_y + y_rel

        return [global_x, global_y]

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Webcam Stream</title>
        <style>
            #videoCanvas { position: absolute; top: 50px; left: 50px; }
            #overlayCanvas { position: absolute; top: 50px; left: 50px; }
            #sendButton { position: absolute; top: 550px; left: 50px; }
        </style>
    </head>
    <body>
        <h1>‎ ‎ ‎ ‎ ‎ ‎ </h1>
        <img src="/video_feed" width="640" height="480" id="videoCanvas">
        <canvas id="overlayCanvas" width="640" height="480"></canvas>
        <button id="sendButton">‎ ‎ ‎ ‎ ‎ ‎ ‎ </button>
        <script>
            const video = document.getElementById('videoCanvas');
            const canvas = document.getElementById('overlayCanvas');
            const ctx = canvas.getContext('2d');
            const sendButton = document.getElementById('sendButton');
            let clicks = [];

            canvas.addEventListener('click', (e) => {
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                // Draw red dot
                ctx.fillStyle = 'red';
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, 2 * Math.PI);
                ctx.fill();

                // Send click coordinates to server
                fetch('/add_point', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({x: x, y: y})
                }).then(response => response.json())
                  .then(data => {
                      console.log('Point added:', data);
                  });
            });

            sendButton.addEventListener(' SEND_OUTAGE', () => {
                fetch('/send_outage', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({})
                }).then(response => response.json())
                  .then(data => {
                      console.log('Outage points sent:', data);
                  });
            });
        </script>
    </body>
    </html>
    '''

@app.route('/upload', methods=['POST'])
def upload_frame():
    global latest_frame, camera_coords
    if 'frame' not in request.files:
        return "No frame uploaded", 400
    frame = request.files['frame'].read()
    with frame_lock:
        latest_frame = frame
    if 'camera_coords' in request.form:
        with coords_lock:
            camera_coords = json.loads(request.form['camera_coords'])
    return "Frame received", 200

@app.route('/add_point', methods=['POST'])
def add_point():
    global outage_points
    data = request.get_json()
    x_pixel = data['x']
    y_pixel = data['y']
    global_pos = pixel_to_global(x_pixel, y_pixel)
    if global_pos:
        outage_points.append(global_pos)
        return jsonify({"status": "success", "point": global_pos}), 200
    return jsonify({"status": "error", "message": "No camera coords"}), 400

@app.route('/send_outage', methods=['POST', 'GET'])
def send_outage():
    global outage_points
    if request.method == 'POST':
        # Clear points after sending
        points_to_send = outage_points.copy()
        outage_points = []
        return jsonify({"points": points_to_send}), 200
    return jsonify({"points": outage_points}), 200

def generate_frames():
    global latest_frame
    while True:
        with frame_lock:
            if latest_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=True)
