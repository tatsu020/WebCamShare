import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
from .camera import Camera, get_available_cameras, get_camera_diagnostics
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
        self.camera_display_to_id = {}
        self._last_camera_issue = "No available camera"
        self.photo_image = None
        self.preview_update_id = None
        self._refreshing = False
        self._starting = False
        self._stopping = False
        self.preview_enabled = True

        self.setup_ui()
        self.refresh_camera_list()

    def setup_ui(self):
        # Header section
        self.frame_header = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_header.pack(fill="x", padx=Theme.PAD_LG, pady=(Theme.PAD_MD, Theme.PAD_SM))

        # Back button
        self.btn_back = ctk.CTkButton(
            self.frame_header,
            text="<",
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
            text="Sender Mode", 
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
            text="R", 
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
            text="Start Streaming", 
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
        self.preview_canvas.pack(fill="both", expand=True, padx=Theme.PAD_SM, pady=(0, Theme.PAD_SM))
        
        # Preview header with toggle button
        self.frame_preview_header = ctk.CTkFrame(self.frame_preview, fg_color="transparent")
        self.frame_preview_header.pack(fill="x", padx=Theme.PAD_SM, pady=(Theme.PAD_SM, 0))
        
        self.label_preview_title = ctk.CTkLabel(
            self.frame_preview_header,
            text="Camera Preview",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_preview_title.pack(side="left", padx=Theme.PAD_XS)
        
        self.btn_preview_toggle = ctk.CTkButton(
            self.frame_preview_header,
            text="Preview",
            width=28,
            height=28,
            font=(Theme.FONT_FAMILY, 14),
            fg_color="transparent",
            hover_color=Theme.BG_INPUT,
            text_color=Theme.ACCENT,
            corner_radius=Theme.RADIUS_SM,
            command=self.toggle_preview
        )
        self.btn_preview_toggle.pack(side="right", padx=Theme.PAD_XS)

        self.preview_text = self.preview_canvas.create_text(
            0, 0, 
            text="Camera Preview", 
            fill=Theme.TEXT_SECONDARY, 
            font=Theme.FONT_BODY, 
            anchor="center"
        )
        
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
    
    def _on_canvas_resize(self, event):
        """Keep preview placeholder centered when the canvas size changes."""
        self.preview_canvas.coords(self.preview_text, event.width // 2, event.height // 2)

    def refresh_camera_list(self):
        """Refresh the camera list using current diagnostics."""
        if self._refreshing or self.is_running or self._starting:
            return
        self._refreshing = True
        self.btn_refresh.configure(state="disabled")

        def worker():
            cameras = get_available_cameras(force_refresh=True)
            diagnostics = get_camera_diagnostics(force_refresh=False)
            self.master.after(0, lambda: self._apply_camera_list(cameras, diagnostics))

        threading.Thread(target=worker, daemon=True).start()

    def _build_camera_display_entries(self, cameras):
        display_items = []
        self.camera_display_to_id = {}

        total_by_name = {}
        for cam in cameras:
            name = str(cam.get("name", "")).strip() or "Unnamed Camera"
            total_by_name[name] = total_by_name.get(name, 0) + 1

        seen_by_name = {}
        for cam in cameras:
            name = str(cam.get("name", "")).strip() or "Unnamed Camera"
            cam_id = str(cam.get("id", ""))
            seen_by_name[name] = seen_by_name.get(name, 0) + 1
            ordinal = seen_by_name[name]

            display_name = name if total_by_name[name] == 1 else f"{name} ({ordinal})"
            display_items.append(display_name)
            self.camera_display_to_id[display_name] = cam_id

        return display_items

    def _build_no_camera_message(self, diagnostics):
        if not diagnostics:
            self._last_camera_issue = "No camera could be opened. Check privacy settings and close other camera apps."
            return self._last_camera_issue

        reason_counts = {}
        for item in diagnostics:
            reason = str(item.get("availability", "unknown"))
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        total = len(diagnostics)
        if reason_counts.get("permission_denied", 0) == total:
            self._last_camera_issue = "Camera access denied by Windows privacy settings."
        elif reason_counts.get("busy", 0) > 0:
            self._last_camera_issue = "Camera detected but currently in use by another app."
        elif reason_counts.get("open_failed", 0) > 0:
            self._last_camera_issue = "Camera detected but failed to open."
        else:
            self._last_camera_issue = "No available camera."

        print(f"Camera diagnostics summary: {reason_counts}")
        return self._last_camera_issue

    def _apply_camera_list(self, cameras, diagnostics):
        self._refreshing = False
        self.camera_list = cameras
        camera_names = self._build_camera_display_entries(self.camera_list)

        if camera_names:
            self.combo_camera.configure(values=camera_names)
            self.camera_var.set(camera_names[0])
            self._last_camera_issue = ""
        else:
            message = self._build_no_camera_message(diagnostics)
            self.camera_display_to_id = {}
            self.combo_camera.configure(values=[message])
            self.camera_var.set(message)

        if not self.is_running and not self._starting:
            self.btn_refresh.configure(state="normal")

    def get_selected_camera_key(self):
        """Return selected camera key."""
        selected = self.camera_var.get()
        if selected in self.camera_display_to_id:
            return self.camera_display_to_id[selected]
        return self.camera_list[0]['id'] if self.camera_list else None

    def toggle_streaming(self):
        if not self.is_running:
            self.start_streaming()
        else:
            self.stop_streaming()

    def start_streaming(self):
        if self._starting or self.is_running:
            return
        self._starting = True
        self.btn_toggle.configure(text="Starting...", state="disabled")
        self.combo_camera.configure(state="disabled")
        self.btn_refresh.configure(state="disabled")

        cam_key = self.get_selected_camera_key()
        if not cam_key:
            self._on_start_failed(RuntimeError(self._last_camera_issue or "No available camera."))
            return

        def worker():
            try:
                camera = Camera(descriptor_key=cam_key)
                camera.start()

                server = StreamServer(camera)
                server.start()
            except Exception as e:
                self.master.after(0, lambda: self._on_start_failed(e))
                return

            self.master.after(0, lambda: self._on_start_success(camera, server))

        threading.Thread(target=worker, daemon=True).start()

    def _on_start_success(self, camera, server):
        self.camera = camera
        self.server = server
        self.is_running = True
        self._starting = False
        self.btn_toggle.configure(
            text="Stop Streaming",
            fg_color=Theme.ACCENT_DANGER,
            hover_color=Theme.ACCENT_DANGER_HOVER,
            state="normal"
        )
        self.combo_camera.configure(state="disabled")
        self.btn_refresh.configure(state="disabled")
        self.update_preview()

    def _on_start_failed(self, error):
        self._starting = False
        self.is_running = False
        self.btn_toggle.configure(
            text="Start Streaming",
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            state="normal"
        )
        self.combo_camera.configure(state="readonly")
        self.btn_refresh.configure(state="normal")
        print(f"Error starting stream: {error}")

    def stop_streaming(self):
        if self._stopping:
            return
        self.is_running = False
        self._stopping = True
        
        if self.preview_update_id:
            self.after_cancel(self.preview_update_id)
            self.preview_update_id = None

        self.photo_image = None
        self.btn_toggle.configure(
            text="Start Streaming", 
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            state="disabled"
        )
        
        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text="Camera Preview")

        def worker():
            if self.server:
                self.server.stop()
                self.server = None
            if self.camera:
                self.camera.stop()
                self.camera = None
            self.master.after(0, self._on_stop_complete)

        threading.Thread(target=worker, daemon=True).start()

    def _on_stop_complete(self):
        self._stopping = False
        if not self.is_running and not self._starting:
            self.btn_toggle.configure(state="normal")
            self.combo_camera.configure(state="readonly")
            if not self._refreshing:
                self.btn_refresh.configure(state="normal")

    def toggle_preview(self):
        """Toggle preview visibility."""
        self.preview_enabled = not self.preview_enabled
        if self.preview_enabled:
            self.btn_preview_toggle.configure(text="Preview", text_color=Theme.ACCENT)
        else:
            self.btn_preview_toggle.configure(text="Preview", text_color=Theme.TEXT_SECONDARY)
            self.preview_canvas.delete("preview")
            self.preview_canvas.itemconfig(self.preview_text, text="Preview Disabled")
    
    def _is_minimized(self):
        """Return True when the window is minimized."""
        try:
            return self.master.state() == "iconic"
        except Exception:
            return False

    def update_preview(self):
        if not self.is_running or not self.camera:
            return
        
        # 繝励Ξ繝薙Η繝ｼ辟｡蜉ｹ譎ゅ∪縺溘・譛蟆丞喧譎ゅ・譖ｴ譁ｰ繧偵せ繧ｭ繝・・
        if not self.preview_enabled or self._is_minimized():
            if not self.preview_enabled:
                self.preview_canvas.delete("preview")
                self.preview_canvas.itemconfig(self.preview_text, text="Preview Disabled")
            else:
                # 譛蟆丞喧荳ｭ
                self.preview_canvas.delete("preview")
                self.preview_canvas.itemconfig(self.preview_text, text="Minimized (Preview Paused)")
            
            self.preview_update_id = self.after(100, self.update_preview)
            return

        frame = self.camera.get_frame_view()
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
                preview_width = max(1, int(w * ratio))
                preview_height = max(1, int(h * ratio))
                frame_resized = cv2.resize(frame, (preview_width, preview_height))
                
                # Convert to RGB for Pillow
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame_rgb)

                # PhotoImage繧剃ｿ晄戟縺励※繧ｬ繝吶・繧ｸ繧ｳ繝ｬ繧ｯ繧ｷ繝ｧ繝ｳ繧帝亟縺・
                self.photo_image = ImageTk.PhotoImage(image)
                
                # Canvas縺ｫ謠冗判
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
