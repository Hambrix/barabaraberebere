from flask import Flask, Response
import cv2
import os

app = Flask(__name__)

# Initialize webcam
camera = cv2.VideoCapture(0)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        # Encode frame as JPEG
        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()
        # Yield frame in MJPEG format
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # For local testing, use host='0.0.0.0' to allow external access if needed
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), threaded=True)