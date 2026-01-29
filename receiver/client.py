import cv2
import numpy as np
import requests

class StreamClient:
    MAX_BUFFER_SIZE = 1024 * 1024  # 1MB制限

    def __init__(self, url):
        self.url = url
        self.stream = None
        self._buffer = bytearray()  # bytearrayに変更（効率的な追加・削除）
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

        for chunk in self.stream.iter_content(chunk_size=65536):  # 64KB（100回→数回のイテレーション）
            if not self.running:
                break

            self._buffer.extend(chunk)

            # バッファサイズ制限（メモリリーク防止）
            if len(self._buffer) > self.MAX_BUFFER_SIZE:
                start = self._buffer.find(b'\xff\xd8')
                if start > 0:
                    del self._buffer[:start]

            # フレーム抽出ループ（複数フレームが蓄積している場合に対応）
            while True:
                a = self._buffer.find(b'\xff\xd8')  # JPEG start
                b = self._buffer.find(b'\xff\xd9', a if a != -1 else 0)  # JPEG end

                if a == -1 or b == -1:
                    break

                jpg = bytes(self._buffer[a:b+2])
                del self._buffer[:b+2]

                try:
                    frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        yield frame
                except Exception:
                    continue
