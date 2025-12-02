from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import threading
import time

class MJPEGHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            try:
                while True:
                    frame = self.server.camera.get_jpeg_frame()
                    if frame:
                        self.wfile.write(b'--frame\r\n')
                        self.send_header('Content-type', 'image/jpeg')
                        self.send_header('Content-length', len(frame))
                        self.end_headers()
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                    else:
                        time.sleep(0.01)
                    # Control framerate slightly to avoid overwhelming network
                    time.sleep(0.01) 
            except Exception as e:
                print(f"Client disconnected: {e}")
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

    def start(self):
        if self.running:
            return
        
        self.server = ThreadedHTTPServer((self.host, self.port), MJPEGHandler)
        self.server.camera = self.camera
        self.running = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"Server started at http://{self.host}:{self.port}/stream.mjpg")

    def stop(self):
        if self.server and self.running:
            self.running = False
            self.server.shutdown()
            self.server.server_close()
            self.server = None
