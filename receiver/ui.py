import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
from .client import StreamClient
from .virtual_cam import VirtualCamera
import tkinter as tk

class ReceiverApp(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack(fill="both", expand=True)

        self.client = None
        self.virtual_cam = None
        self.is_running = False
        self.thread = None
        self.photo_image = None  # PhotoImage参照を保持

        self.setup_ui()

    def setup_ui(self):
        # Title
        self.label_title = ctk.CTkLabel(self, text="Virtual Camera Receiver", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=10)

        # Controls
        self.frame_controls = ctk.CTkFrame(self)
        self.frame_controls.pack(pady=10)

        self.label_ip = ctk.CTkLabel(self.frame_controls, text="Sender IP:")
        self.label_ip.pack(side="left", padx=5)

        self.entry_ip = ctk.CTkEntry(self.frame_controls, width=120)
        self.entry_ip.insert(0, "192.168.1.X")
        self.entry_ip.pack(side="left", padx=5)

        self.btn_connect = ctk.CTkButton(self.frame_controls, text="Connect", command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=10)

        # Status
        self.label_status = ctk.CTkLabel(self, text="Status: Disconnected", text_color="gray")
        self.label_status.pack(pady=5)

        # Preview - Canvasを使用
        self.preview_canvas = tk.Canvas(self, width=640, height=360, bg="black", highlightthickness=0)
        self.preview_canvas.pack(pady=10, fill="both", expand=True)
        self.preview_text = self.preview_canvas.create_text(0, 0, text="Preview", fill="white", font=("Arial", 16), anchor="center")
        
        # Canvasサイズ変更時にテキストを中央に配置
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
    
    def _on_canvas_resize(self, event):
        """Canvasサイズ変更時にテキストを中央に移動"""
        self.preview_canvas.coords(self.preview_text, event.width // 2, event.height // 2)

    def toggle_connection(self):
        if not self.is_running:
            self.start_receiving()
        else:
            self.stop_receiving()

    def start_receiving(self):
        ip = self.entry_ip.get()
        url = f"http://{ip}:8000/stream.mjpg"
        
        try:
            self.client = StreamClient(url)
            self.client.start()
            
            # Initialize Virtual Camera (Standard HD resolution)
            self.virtual_cam = VirtualCamera(width=1280, height=720)
            self.virtual_cam.start()

            self.is_running = True
            self.btn_connect.configure(text="Disconnect", fg_color="red")
            self.label_status.configure(text="Status: Connected", text_color="green")
            
            self.thread = threading.Thread(target=self.process_stream, daemon=True)
            self.thread.start()

        except Exception as e:
            self.label_status.configure(text=f"Error: {e}", text_color="red")
            self.stop_receiving()

    def stop_receiving(self):
        self.is_running = False
        if self.client:
            self.client.stop()
            self.client = None
        if self.virtual_cam:
            self.virtual_cam.stop()
            self.virtual_cam = None
        
        self.photo_image = None
        self.btn_connect.configure(text="Connect", fg_color=["#3B8ED0", "#1F6AA5"])
        self.label_status.configure(text="Status: Disconnected", text_color="gray")
        
        # Canvasをクリアしてテキスト表示
        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text="Preview Stopped")

    def process_stream(self):
        if not self.client:
            return

        for frame in self.client.get_frames():
            if not self.is_running:
                break
            
            # Send to Virtual Camera
            if self.virtual_cam:
                self.virtual_cam.send_frame(frame)

            # Update Preview (run on main thread)
            self.master.after(0, self.update_preview_image, frame)

    def update_preview_image(self, frame):
        if not self.is_running:
            return
        
        try:
            # Convert to RGB for Pillow
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            
            # Resize for preview
            canvas_width = self.preview_canvas.winfo_width()
            canvas_height = self.preview_canvas.winfo_height()
            if canvas_width < 10:
                canvas_width = 640
            if canvas_height < 10:
                canvas_height = 360
            
            ratio = min(canvas_width / image.width, canvas_height / image.height)
            preview_width = int(image.width * ratio)
            preview_height = int(image.height * ratio)
            image = image.resize((preview_width, preview_height), Image.Resampling.LANCZOS)

            # PhotoImageを保持してガベージコレクションを防ぐ
            self.photo_image = ImageTk.PhotoImage(image)
            
            # Canvasに描画
            self.preview_canvas.delete("preview")
            self.preview_canvas.itemconfig(self.preview_text, text="")
            x = canvas_width // 2
            y = canvas_height // 2
            self.preview_canvas.create_image(x, y, image=self.photo_image, tag="preview")
        except Exception as e:
            print(f"Preview error: {e}")
