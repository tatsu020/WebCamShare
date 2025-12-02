import cv2
import threading
import time
import os

def get_camera_names():
    """Windowsでカメラのデバイス名を取得する"""
    try:
        from pygrabber.dshow_graph import FilterGraph
        graph = FilterGraph()
        return graph.get_input_devices()
    except Exception:
        return []

def get_available_cameras(max_cameras=5):
    """利用可能なカメラの一覧を取得する"""
    cameras = []
    
    # OpenCVのエラー出力を一時的に抑制
    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
    
    # Windowsのデバイス名を取得
    device_names = get_camera_names()
    
    for i in range(max_cameras):
        # DirectShowバックエンドを使用（Windowsで安定）
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            # フレームが実際に取得できるか確認
            ret, _ = cap.read()
            if ret:
                # デバイス名があれば使用、なければ番号
                if i < len(device_names):
                    name = device_names[i]
                else:
                    name = f"Camera {i}"
                cameras.append({
                    'id': i,
                    'name': name
                })
            cap.release()
        else:
            cap.release()
    
    return cameras

class Camera:
    def __init__(self, camera_id=0, width=1280, height=720):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.cap = None
        self.running = False
        self.thread = None
        self.current_frame = None
        self.lock = threading.Lock()

    def start(self):
        if self.running:
            return
        
        # DirectShowバックエンドを使用（Windowsで安定）
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {self.camera_id}")

        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        if self.cap:
            self.cap.release()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.current_frame = frame
            else:
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def get_jpeg_frame(self):
        frame = self.get_frame()
        if frame is not None:
            ret, jpeg = cv2.imencode('.jpg', frame)
            if ret:
                return jpeg.tobytes()
        return None
