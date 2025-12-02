import cv2
import numpy as np
import requests

class StreamClient:
    def __init__(self, url):
        self.url = url
        self.stream = None
        self.bytes = b''
        self.running = False

    def start(self):
        self.running = True
        try:
            self.stream = requests.get(self.url, stream=True, timeout=5)
            if self.stream.status_code != 200:
                raise ConnectionError(f"Could not connect to {self.url}")
        except Exception as e:
            self.running = False
            raise e

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.close()

    def get_frames(self):
        """Generator that yields frames from the stream."""
        if not self.stream:
            return

        for chunk in self.stream.iter_content(chunk_size=1024):
            if not self.running:
                break
            
            self.bytes += chunk
            a = self.bytes.find(b'\xff\xd8') # JPEG start
            b = self.bytes.find(b'\xff\xd9') # JPEG end
            
            if a != -1 and b != -1:
                jpg = self.bytes[a:b+2]
                self.bytes = self.bytes[b+2:]
                
                try:
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        yield frame
                except Exception:
                    continue
