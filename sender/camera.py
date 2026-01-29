import os
import sys

# OpenCVの不要なログを抑制 (cv2をインポートする前に設定する必要がある)
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_PRIORITY_LIST"] = "DSHOW,MSMF"
os.environ["OPENCV_VIDEOIO_OBSENSOR_BACKEND_PRIORITY"] = "0"

import cv2
import threading
import time
import pythoncom

def get_camera_names():
    """DirectShowのインデックス順にカメラ名を取得する"""
    devices = []
    
    # 1. pygrabber (DirectShow Graph) を使用
    # これが OpenCV (CAP_DSHOW) のインデックスと最も一致する
    try:
        import pythoncom
        pythoncom.CoInitialize()
        from pygrabber.dshow_graph import FilterGraph
        graph = FilterGraph()
        devices = graph.get_input_devices()
        if devices:
            return devices
    except Exception:
        pass

    # 2. フォールバック: PowerShell
    try:
        import subprocess
        import json
        cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-PnpDevice -Class Camera,Image,Video -Status OK | Select-Object -ExpandProperty FriendlyName | ConvertTo-Json"'
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            raw_data = json.loads(result.stdout)
            if isinstance(raw_data, list):
                return raw_data
            elif isinstance(raw_data, str):
                return [raw_data]
    except Exception:
        pass
            
    return []

def get_available_cameras():
    """利用可能なカメラの一覧を取得する（高速版）"""
    # DirectShowバックエンドでのデバイス名リストを取得
    # 一台ずつVideoCaptureを開くと非常に遅く、LEDが点滅するため、
    # システムのデバイス一覧をそのまま信頼する。
    device_names = get_camera_names()

    cameras = []
    for i, name in enumerate(device_names):
        cameras.append({
            'id': i,
            'name': name
        })

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

        # Zero-Copy設計: JPEG圧縮済みバッファ
        self._jpeg_buffer = None
        self._jpeg_lock = threading.Lock()
        self._encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]

    def start(self):
        if self.running:
            return

        # DirectShowを使用（名前のインデックスと一致させるため）
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        
        if self.cap.isOpened():
            # バッファサイズを最小にして遅延を抑制
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # デバイス側のデフォルト解像度を取得して保持（アプリ側から変更しない）
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            print(f"Camera opened at: {self.width}x{self.height}")

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
                # JPEG圧縮をカメラスレッドで事前実行（メインスレッドの負荷軽減）
                ret_enc, jpeg = cv2.imencode('.jpg', frame, self._encode_params)
                if ret_enc:
                    with self._jpeg_lock:
                        self._jpeg_buffer = jpeg.tobytes()
                with self.lock:
                    self.current_frame = frame
            else:
                time.sleep(0.1)

    def get_frame(self):
        """フレームのコピーを返す（外部で変更する場合用）"""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def get_frame_view(self):
        """プレビュー用（コピーなし参照、読み取り専用）"""
        with self.lock:
            return self.current_frame

    def get_jpeg_frame(self):
        """互換性維持用（非推奨）"""
        return self.get_jpeg_frame_direct()

    def get_jpeg_frame_direct(self):
        """圧縮済みJPEGバッファを直接返す（Zero-Copy）"""
        with self._jpeg_lock:
            return self._jpeg_buffer
