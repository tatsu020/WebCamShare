import customtkinter as ctk
import cv2
from PIL import Image, ImageTk
from .camera import Camera, get_available_cameras
from .server import StreamServer
from utils.network import get_local_ip
import tkinter as tk

class SenderApp(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack(fill="both", expand=True)

        self.camera = None
        self.server = None
        self.is_running = False
        self.camera_list = []
        self.photo_image = None  # PhotoImage参照を保持
        self.preview_update_id = None  # afterのIDを保持

        self.setup_ui()
        self.refresh_camera_list()

    def setup_ui(self):
        # Title
        self.label_title = ctk.CTkLabel(self, text="Webcam Sender", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=10)

        # IP Info
        local_ip = get_local_ip()
        self.label_ip = ctk.CTkLabel(self, text=f"Stream URL: http://{local_ip}:8000/stream.mjpg")
        self.label_ip.pack(pady=5)

        # Controls
        self.frame_controls = ctk.CTkFrame(self)
        self.frame_controls.pack(pady=10)

        self.label_cam_id = ctk.CTkLabel(self.frame_controls, text="Camera:")
        self.label_cam_id.pack(side="left", padx=5)

        self.camera_var = ctk.StringVar(value="カメラを選択...")
        self.combo_camera = ctk.CTkComboBox(
            self.frame_controls, 
            width=250,
            variable=self.camera_var,
            values=[],
            state="readonly"
        )
        self.combo_camera.pack(side="left", padx=5)

        self.btn_refresh = ctk.CTkButton(
            self.frame_controls, 
            text="🔄", 
            width=30, 
            command=self.refresh_camera_list
        )
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_toggle = ctk.CTkButton(self.frame_controls, text="Start Streaming", command=self.toggle_streaming)
        self.btn_toggle.pack(side="left", padx=10)

        # Preview - Canvasを使用
        self.preview_canvas = tk.Canvas(self, width=640, height=360, bg="black", highlightthickness=0)
        self.preview_canvas.pack(pady=10, fill="both", expand=True)
        self.preview_text = self.preview_canvas.create_text(0, 0, text="Preview", fill="white", font=("Arial", 16), anchor="center")
        
        # Canvasサイズ変更時にテキストを中央に配置
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
    
    def _on_canvas_resize(self, event):
        """Canvasサイズ変更時にテキストを中央に移動"""
        self.preview_canvas.coords(self.preview_text, event.width // 2, event.height // 2)

    def refresh_camera_list(self):
        """カメラ一覧を更新"""
        self.camera_list = get_available_cameras()
        camera_names = [cam['name'] for cam in self.camera_list]
        
        if camera_names:
            self.combo_camera.configure(values=camera_names)
            self.camera_var.set(camera_names[0])
        else:
            self.combo_camera.configure(values=["カメラが見つかりません"])
            self.camera_var.set("カメラが見つかりません")

    def get_selected_camera_id(self):
        """選択されたカメラのIDを取得"""
        selected = self.camera_var.get()
        for cam in self.camera_list:
            if cam['name'] == selected:
                return cam['id']
        return 0

    def toggle_streaming(self):
        if not self.is_running:
            self.start_streaming()
        else:
            self.stop_streaming()

    def start_streaming(self):
        try:
            cam_id = self.get_selected_camera_id()
            self.camera = Camera(camera_id=cam_id)
            self.camera.start()

            self.server = StreamServer(self.camera)
            self.server.start()

            self.is_running = True
            self.btn_toggle.configure(text="Stop Streaming", fg_color="red")
            self.combo_camera.configure(state="disabled")
            self.btn_refresh.configure(state="disabled")
            self.update_preview()
        except Exception as e:
            print(f"Error starting stream: {e}")

    def stop_streaming(self):
        self.is_running = False
        
        # プレビュー更新をキャンセル
        if self.preview_update_id:
            self.after_cancel(self.preview_update_id)
            self.preview_update_id = None
        
        if self.server:
            self.server.stop()
            self.server = None
        if self.camera:
            self.camera.stop()
            self.camera = None
        
        self.photo_image = None
        self.btn_toggle.configure(text="Start Streaming", fg_color=["#3B8ED0", "#1F6AA5"])
        self.combo_camera.configure(state="readonly")
        self.btn_refresh.configure(state="normal")
        
        # Canvasをクリアしてテキスト表示
        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text="Preview Stopped")

    def update_preview(self):
        if not self.is_running or not self.camera:
            return
        
        frame = self.camera.get_frame()
        if frame is not None:
            try:
                # Convert to RGB for Pillow
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)
                
                # Resize for preview (keep aspect ratio)
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
        
        self.preview_update_id = self.after(30, self.update_preview)
