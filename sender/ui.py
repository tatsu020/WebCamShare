import customtkinter as ctk
import cv2
from PIL import Image, ImageTk
from .camera import Camera, get_available_cameras
from .server import StreamServer
from utils.network import get_local_ip
from utils.theme import Theme
import tkinter as tk

class SenderApp(ctk.CTkFrame):
    def __init__(self, master, on_back=None):
        super().__init__(master, fg_color=Theme.BG_DARK)
        self.master = master
        self.on_back = on_back
        self.pack(fill="both", expand=True)

        self.camera = None
        self.server = None
        self.is_running = False
        self.camera_list = []
        self.photo_image = None
        self.preview_update_id = None

        self.setup_ui()
        self.refresh_camera_list()

    def setup_ui(self):
        # Header section
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.pack(fill="x", padx=Theme.PAD_LG, pady=(Theme.PAD_MD, Theme.PAD_SM))

        # Back button
        self.btn_back = ctk.CTkButton(
            self.frame_header,
            text="←",
            width=36,
            height=36,
            font=(Theme.FONT_FAMILY, 18),
            fg_color=Theme.BG_INPUT,
            hover_color="#3a3a46",
            corner_radius=Theme.RADIUS_SM,
            command=self._on_back
        )
        self.btn_back.pack(side="left", padx=(0, Theme.PAD_SM))

        self.label_title = ctk.CTkLabel(
            self.frame_header, 
            text="📷 Sender Mode", 
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_PRIMARY
        )
        self.label_title.pack(side="left")

        # Stream URL display
        local_ip = get_local_ip()
        self.frame_url = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM
        )
        self.frame_url.pack(fill="x", padx=Theme.PAD_LG, pady=Theme.PAD_SM)

        self.label_url_prefix = ctk.CTkLabel(
            self.frame_url, 
            text="Stream URL", 
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_url_prefix.pack(anchor="w", padx=Theme.PAD_MD, pady=(Theme.PAD_SM, 0))

        self.label_ip = ctk.CTkLabel(
            self.frame_url, 
            text=f"http://{local_ip}:8000/stream.mjpg",
            font=(Theme.FONT_FAMILY, 13, "bold"),
            text_color=Theme.TEXT_ACCENT
        )
        self.label_ip.pack(anchor="w", padx=Theme.PAD_MD, pady=(0, Theme.PAD_SM))

        # Controls card
        self.frame_controls = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM
        )
        self.frame_controls.pack(fill="x", padx=Theme.PAD_LG, pady=Theme.PAD_SM)

        self.frame_controls_inner = ctk.CTkFrame(self.frame_controls, fg_color="transparent")
        self.frame_controls_inner.pack(fill="x", padx=Theme.PAD_MD, pady=Theme.PAD_MD)

        self.label_cam_id = ctk.CTkLabel(
            self.frame_controls_inner, 
            text="Camera",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_cam_id.pack(side="left", padx=(0, Theme.PAD_SM))

        self.camera_var = ctk.StringVar(value="Select camera...")
        self.combo_camera = ctk.CTkComboBox(
            self.frame_controls_inner, 
            width=280,
            height=36,
            variable=self.camera_var,
            values=[],
            state="readonly",
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_INPUT,
            border_width=0,
            button_color=Theme.ACCENT,
            button_hover_color=Theme.ACCENT_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM
        )
        self.combo_camera.pack(side="left", padx=Theme.PAD_XS)

        self.btn_refresh = ctk.CTkButton(
            self.frame_controls_inner, 
            text="↻", 
            width=36,
            height=36,
            font=(Theme.FONT_FAMILY, 16),
            fg_color=Theme.BG_INPUT,
            hover_color="#2d2d3d",
            corner_radius=Theme.RADIUS_SM,
            command=self.refresh_camera_list
        )
        self.btn_refresh.pack(side="left", padx=Theme.PAD_XS)

        self.btn_toggle = ctk.CTkButton(
            self.frame_controls_inner, 
            text="▶  Start Streaming", 
            height=36,
            width=160,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS_SM,
            command=self.toggle_streaming
        )
        self.btn_toggle.pack(side="right", padx=Theme.PAD_XS)

        # Preview area
        self.frame_preview = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_MD
        )
        self.frame_preview.pack(fill="both", expand=True, padx=Theme.PAD_LG, pady=Theme.PAD_MD)

        self.preview_canvas = tk.Canvas(
            self.frame_preview, 
            width=640, 
            height=360, 
            bg=Theme.BG_PREVIEW, 
            highlightthickness=0
        )
        self.preview_canvas.pack(fill="both", expand=True, padx=Theme.PAD_SM, pady=Theme.PAD_SM)
        self.preview_text = self.preview_canvas.create_text(
            0, 0, 
            text="Camera Preview", 
            fill=Theme.TEXT_SECONDARY, 
            font=Theme.FONT_BODY, 
            anchor="center"
        )
        
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
            self.btn_toggle.configure(
                text="■  Stop Streaming", 
                fg_color=Theme.ACCENT_DANGER,
                hover_color=Theme.ACCENT_DANGER_HOVER
            )
            self.combo_camera.configure(state="disabled")
            self.btn_refresh.configure(state="disabled")
            self.update_preview()
        except Exception as e:
            print(f"Error starting stream: {e}")

    def stop_streaming(self):
        self.is_running = False
        
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
        self.btn_toggle.configure(
            text="▶  Start Streaming", 
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER
        )
        self.combo_camera.configure(state="readonly")
        self.btn_refresh.configure(state="normal")
        
        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text="Camera Preview")

    def update_preview(self):
        if not self.is_running or not self.camera:
            return
        
        frame = self.camera.get_frame()
        if frame is not None:
            try:
                # Resize for preview (keep aspect ratio) using cv2 for performance
                canvas_width = self.preview_canvas.winfo_width()
                canvas_height = self.preview_canvas.winfo_height()
                if canvas_width < 10:
                    canvas_width = 640
                if canvas_height < 10:
                    canvas_height = 360
                
                h, w = frame.shape[:2]
                ratio = min(canvas_width / w, canvas_height / h)
                preview_width = int(w * ratio)
                preview_height = int(h * ratio)
                frame_resized = cv2.resize(frame, (preview_width, preview_height))
                
                # Convert to RGB for Pillow
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)

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

    def _on_back(self):
        """Handle back button click"""
        if self.on_back:
            self.on_back()

    def cleanup(self):
        """Clean up resources before destroying"""
        self.stop_streaming()
