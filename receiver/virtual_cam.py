import pyvirtualcam
import cv2
import numpy as np

class VirtualCamera:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.cam = None

    def start(self):
        try:
            # Auto-detect OBS Virtual Camera or other available drivers
            self.cam = pyvirtualcam.Camera(width=self.width, height=self.height, fps=self.fps)
            print(f'Virtual camera started: {self.cam.device}')
        except Exception as e:
            raise RuntimeError(f"Could not start virtual camera. Make sure OBS Virtual Camera is installed. Error: {e}")

    def send_frame(self, frame):
        if self.cam:
            # pyvirtualcam expects RGB, OpenCV gives BGR
            # Also need to resize if frame size doesn't match
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.cam.send(frame_rgb)
            self.cam.sleep_until_next_frame()

    def stop(self):
        if self.cam:
            self.cam.close()
            self.cam = None
