from flask import Flask, Response, request
import os
import threading

app = Flask(__name__)

# Store the latest frame (thread-safe)
latest_frame = None
frame_lock = threading.Lock()

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Webcam Stream</title>
    </head>
    <body>
        <h1>Live Webcam Stream</h1>
        <img src="/video_feed" style="width:640px;height:480px;">
    </body>
    </html>
    '''

@app.route('/upload', methods=['POST'])
def upload_frame():
    global latest_frame
    if 'frame' not in request.files:
        return "No frame uploaded", 400
    frame = request.files['frame'].read()
    with frame_lock:
        latest_frame = frame
    return "Frame received", 200

def generate_frames():
    global latest_frame
    while True:
        with frame_lock:
            if latest_frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
        # Avoid overwhelming the server
        import time
        time.sleep(0.05)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=True)
