from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import time
from utils.network import ServerAnnouncer

class MJPEGHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """HTTPサーバーのログを抑制（Nuitkaビルドでstdout問題を回避）"""
        pass

    def do_GET(self):
        if self.path == '/stream.mjpg' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()

            target_interval = 1.0 / 30  # 30fps目標
            last_frame_time = 0

            try:
                while True:
                    current_time = time.monotonic()
                    elapsed = current_time - last_frame_time

                    # 適応的FPS制御：目標間隔に満たない場合のみスリープ
                    if elapsed < target_interval:
                        time.sleep(target_interval - elapsed)

                    frame = self.server.camera.get_jpeg_frame_direct()
                    if frame:
                        last_frame_time = time.monotonic()
                        # MJPEGフォーマットで直接書き込み（send_headerは使わない）
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame)}\r\n'.encode())
                        self.wfile.write(b'\r\n')
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
            except Exception as e:
                pass  # Client disconnected
        else:
            self.send_response(404)
            self.end_headers()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass

class StreamServer:
    def __init__(self, camera, host='0.0.0.0', port=8000):
        self.camera = camera
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.running = False
        self.announcer = ServerAnnouncer(server_port=port)

    def start(self):
        if self.running:
            return

        self.server = ThreadedHTTPServer((self.host, self.port), MJPEGHandler)
        self.server.camera = self.camera
        self.running = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        # Start server announcer for auto-discovery
        self.announcer.start()

        print(f"Server started at http://{self.host}:{self.port}/stream.mjpg")

    def stop(self):
        if self.server and self.running:
            self.running = False

            # Stop server announcer
            self.announcer.stop()

            self.server.shutdown()
            self.server.server_close()
            self.server = None
