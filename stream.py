import cv2
import aiohttp
import asyncio
import time
from pioneer_sdk import Camera, Pioneer
import threading
import queue
import json

# Configuration
SERVER_URL = "https://barabaraberebere.onrender.com/upload"
WEBSOCKET_URL = "wss://barabaraberebere.onrender.com/outage_ws"
JPEG_QUALITY = 22  # Low quality for minimal size
CAMERA_IP = "127.0.0.1"  # Drone camera IP
CAMERA_PORT = 18000  # Camera port
MAVLINK_PORT = 8000  # Pioneer MAVLink port
FPS = 10  # Target 10 FPS

# Read camera global coordinates from droneinit.txt
try:
    with open("droneinit.txt", "r") as f:
        lines = f.readlines()
        camera_coords = [float(lines[0].strip()), float(lines[1].strip())]  # [X, Y]
except Exception as e:
    print(f"Error reading droneinit.txt: {e}")
    exit()

# Initialize camera and Pioneer
try:
    camera = Camera(ip=CAMERA_IP, port=CAMERA_PORT)
    pioneer = Pioneer(ip=CAMERA_IP, mavlink_port=MAVLINK_PORT, log_connection=False)
except Exception as e:
    print(f"Error initializing Camera or Pioneer: {e}")
    exit()

# Queues for encoding and sending
encode_queue = queue.Queue(maxsize=10)
send_queue = queue.Queue(maxsize=10)

def encode_frames():
    """Thread to encode frames as JPEG"""
    while True:
        try:
            frame, frame_id = encode_queue.get(timeout=1)
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
            ret, buffer = cv2.imencode('.jpg', frame, encode_param)
            if ret:
                send_queue.put((buffer.tobytes(), frame_id))
            encode_queue.task_done()
        except queue.Empty:
            continue
        except KeyboardInterrupt:
            break

async def send_frame(session, buffer, frame_id):
    """Async function to send frame and coordinates to server"""
    try:
        form_data = aiohttp.FormData()
        form_data.add_field("frame", buffer, filename="frame.jpg", content_type="image/jpeg")
        form_data.add_field("camera_coords", json.dumps(camera_coords))
        async with session.post(SERVER_URL, data=form_data) as response:
            if response.status == 200:
                print(f"Frame {frame_id} sent successfully (size: {len(buffer)} bytes)")
            else:
                print(f"Frame {frame_id} failed: {response.status}")
    except Exception as e:
        print(f"Error sending frame {frame_id}: {e}")

async def receive_outage():
    """Receive outage array via WebSocket"""
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(WEBSOCKET_URL) as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        points = data.get("points", [])
                        if points:
                            # Save outage points to file
                            with open("outage_points.txt", "w") as f:
                                for x, y in points:
                                    f.write(f"{x} {y}\n")
                            print(f"Saved outage points: {points}")
                    except Exception as e:
                        print(f"Error processing outage array: {e}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"WebSocket error: {ws.exception()}")

async def main():
    # Start encoding thread
    encode_thread = threading.Thread(target=encode_frames, daemon=True)
    encode_thread.start()

    # Start WebSocket receiver task
    outage_task = asyncio.create_task(receive_outage())

    # Initialize async HTTP session for sending
    async with aiohttp.ClientSession() as session:
        frame_id = 0
        try:
            while True:
                start_time = time.time()

                # Capture frame
                frame = camera.get_cv_frame()
                if frame is None:
                    print(f"Warning: Failed to fetch frame {frame_id}.")
                    await asyncio.sleep(0.1)
                    continue

                # Use full 640x480 resolution
                # frame.shape is (480, 640, 3)

                # Put frame in encoding queue
                try:
                    encode_queue.put_nowait((frame, frame_id))
                except queue.Full:
                    print(f"Warning: Encode queue full, dropping frame {frame_id}.")

                # Send any ready frames
                while not send_queue.empty():
                    buffer, sent_frame_id = send_queue.get_nowait()
                    await send_frame(session, buffer, sent_frame_id)
                    send_queue.task_done()

                # Control FPS
                elapsed = time.time() - start_time
                sleep_time = max(0, (1 / FPS) - elapsed)
                await asyncio.sleep(sleep_time)

                frame_id += 1

        except KeyboardInterrupt:
            print("Stopping client")
            outage_task.cancel()

# Run async main
try:
    asyncio.run(main())
finally:
    # Cleanup
    del camera
    pioneer.close_connection()
