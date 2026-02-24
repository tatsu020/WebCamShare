import customtkinter as ctk
import cv2
import threading
import time
from PIL import Image, ImageTk
from .client import StreamClient
from .virtual_cam import VirtualCamera, diagnose_custom_camera_registration
from utils.network import ServerDiscovery
from utils.theme import Theme
import tkinter as tk

class ReceiverApp(ctk.CTkFrame):
    def __init__(self, master, on_back=None):
        super().__init__(master, fg_color=Theme.BG_DARK)
        self.master = master
        self.on_back = on_back
        self.pack(fill="both", expand=True)

        self.client = None
        self.virtual_cam = None
        self.is_running = False
        self.thread = None
        self.photo_image = None
        self.discovered_servers = []
        self._pending_frame = False
        self._canvas_size = (640, 360)
        self._connecting = False
        self._cancel_connect = False
        self.preview_enabled = True
        self._virtual_cam_retry_sec = 0.5
        self.driver_status = None

        self.setup_ui()
        self.refresh_driver_status()

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
            text="Receiver Mode", 
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_PRIMARY
        )
        self.label_title.pack(side="left")

        # Discovery card
        self.frame_discovery = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM
        )
        self.frame_discovery.pack(fill="x", padx=Theme.PAD_LG, pady=Theme.PAD_SM)

        self.frame_discovery_inner = ctk.CTkFrame(self.frame_discovery, fg_color="transparent")
        self.frame_discovery_inner.pack(fill="x", padx=Theme.PAD_MD, pady=Theme.PAD_MD)

        self.btn_discover = ctk.CTkButton(
            self.frame_discovery_inner, 
            text="🔍  Auto Discover", 
            command=self.discover_servers,
            width=150,
            height=36,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS_SM
        )
        self.btn_discover.pack(side="left", padx=(0, Theme.PAD_SM))

        self.server_dropdown = ctk.CTkComboBox(
            self.frame_discovery_inner,
            values=["No servers found"],
            width=300,
            height=36,
            state="readonly",
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_INPUT,
            border_width=0,
            button_color=Theme.ACCENT,
            button_hover_color=Theme.ACCENT_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM,
            command=self.on_server_selected
        )
        self.server_dropdown.pack(side="left", fill="x", expand=True)

        # Manual connection card
        self.frame_controls = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_SM
        )
        self.frame_controls.pack(fill="x", padx=Theme.PAD_LG, pady=Theme.PAD_SM)

        self.frame_controls_inner = ctk.CTkFrame(self.frame_controls, fg_color="transparent")
        self.frame_controls_inner.pack(fill="x", padx=Theme.PAD_MD, pady=Theme.PAD_MD)

        self.label_ip = ctk.CTkLabel(
            self.frame_controls_inner, 
            text="IP Address",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_ip.pack(side="left", padx=(0, Theme.PAD_SM))

        self.entry_ip = ctk.CTkEntry(
            self.frame_controls_inner, 
            width=180,
            height=36,
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_INPUT,
            border_width=0,
            corner_radius=Theme.RADIUS_SM
        )
        self.entry_ip.insert(0, "192.168.1.X")
        self.entry_ip.pack(side="left", padx=Theme.PAD_XS)

        self.btn_connect = ctk.CTkButton(
            self.frame_controls_inner, 
            text="▶  Connect", 
            command=self.toggle_connection,
            height=36,
            width=140,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS_SM
        )
        self.btn_connect.pack(side="right", padx=Theme.PAD_XS)

        # Driver controls
        self.frame_driver = ctk.CTkFrame(self.frame_controls, fg_color="transparent")
        self.frame_driver.pack(fill="x", padx=Theme.PAD_MD, pady=(0, Theme.PAD_MD))
        
        self.label_driver = ctk.CTkLabel(
            self.frame_driver, text="Custom Driver:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_SECONDARY
        )
        self.label_driver.pack(side="left", padx=(0, Theme.PAD_SM))

        self.btn_reg_driver = ctk.CTkButton(
            self.frame_driver, text="Install", command=self.register_driver,
            width=80, height=28, font=Theme.FONT_SMALL,
            fg_color=Theme.BG_INPUT, hover_color="#3a3a46", border_width=1, border_color=Theme.ACCENT
        )
        self.btn_reg_driver.pack(side="left", padx=(0, Theme.PAD_XS))

        self.btn_unreg_driver = ctk.CTkButton(
            self.frame_driver, text="Uninstall", command=self.unregister_driver,
            width=80, height=28, font=Theme.FONT_SMALL,
            fg_color=Theme.BG_INPUT, hover_color="#3a3a46", border_width=1, border_color=Theme.ACCENT_DANGER
        )
        self.btn_unreg_driver.pack(side="left")

        # Status indicator
        self.frame_status = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_status.pack(fill="x", padx=Theme.PAD_LG, pady=Theme.PAD_XS)

        self.label_status = ctk.CTkLabel(
            self.frame_status, 
            text="Disconnected", 
            font=Theme.FONT_SMALL,
            text_color=Theme.STATUS_IDLE
        )
        self.label_status.pack(side="left")

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
            text="Stream Preview",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_preview_title.pack(side="left", padx=Theme.PAD_XS)
        
        self.btn_preview_toggle = ctk.CTkButton(
            self.frame_preview_header,
            text="👁",
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
            text="Stream Preview", 
            fill=Theme.TEXT_SECONDARY, 
            font=Theme.FONT_BODY, 
            anchor="center"
        )
        
        self.preview_canvas.bind("<Configure>", self._on_canvas_resize)
    
    def _on_canvas_resize(self, event):
        """Keep preview placeholder centered."""
        self.preview_canvas.coords(self.preview_text, event.width // 2, event.height // 2)
        self._canvas_size = (event.width, event.height)

    def refresh_driver_status(self):
        self.driver_status = diagnose_custom_camera_registration()
        status = self.driver_status

        if status.status_code == "ok":
            text = "Custom Driver: Ready"
            color = Theme.STATUS_SUCCESS
        elif status.status_code == "path_mismatch":
            text = "Custom Driver: Path mismatch (Install to repair)"
            color = Theme.STATUS_WARNING
        elif status.status_code == "not_registered":
            text = "Custom Driver: Not registered (Install)"
            color = Theme.STATUS_WARNING
        elif status.status_code == "dll_not_found":
            text = "Custom Driver: DLL not found"
            color = Theme.STATUS_ERROR
        else:
            text = "Custom Driver: Registry check failed"
            color = Theme.STATUS_ERROR

        self.label_driver.configure(text=text, text_color=color)
        print(
            f"[DriverDiagnostic] code={status.status_code} "
            f"dll={status.dll_path} registered={status.registered_path}"
        )

    def register_driver(self):
        from .virtual_cam import register_custom_camera
        ok, _code, message = register_custom_camera()
        if ok:
            self.label_status.configure(text=f"{message}", text_color=Theme.STATUS_SUCCESS)
        else:
            self.label_status.configure(text=f"Install failed: {message}", text_color=Theme.STATUS_ERROR)
        self.refresh_driver_status()

    def unregister_driver(self):
        from .virtual_cam import unregister_custom_camera
        ok, _code, message = unregister_custom_camera()
        if ok:
            self.label_status.configure(text=f"{message}", text_color=Theme.STATUS_SUCCESS)
        else:
            self.label_status.configure(text=f"Uninstall failed: {message}", text_color=Theme.STATUS_ERROR)
        self.refresh_driver_status()

    def toggle_connection(self):
        if not self.is_running and not self._connecting:
            self.start_receiving()
        else:
            self.stop_receiving()

    def discover_servers(self):
        """Auto-discover servers on LAN."""
        self.btn_discover.configure(state="disabled", text="🔍  Searching...")
        self.label_status.configure(text="Searching for servers...", text_color=Theme.STATUS_WARNING)
        
        def search():
            discovery = ServerDiscovery(timeout=3.0)
            servers = discovery.discover()
            self.master.after(0, lambda: self.update_server_list(servers))
        
        threading.Thread(target=search, daemon=True).start()
    
    def update_server_list(self, servers):
        """Update discovered servers in UI."""
        self.btn_discover.configure(state="normal", text="🔍  Auto Discover")
        self.discovered_servers = servers
        
        if servers:
            server_names = [f"{s['name']} - {s['ip']}:{s['port']}" for s in servers]
            self.server_dropdown.configure(values=server_names)
            self.server_dropdown.set(server_names[0])
            
            if len(servers) == 1:
                self.entry_ip.delete(0, "end")
                self.entry_ip.insert(0, servers[0]['ip'])
                self.label_status.configure(
                    text=f"Found: {servers[0]['name']} - Connecting...",
                    text_color=Theme.STATUS_SUCCESS
                )
                self.master.after(100, self.start_receiving)
            else:
                self.label_status.configure(
                    text=f"{len(servers)} servers found - Select from dropdown", 
                    text_color=Theme.STATUS_SUCCESS
                )
        else:
            self.server_dropdown.configure(values=["No servers found"])
            self.server_dropdown.set("No servers found")
            self.label_status.configure(
                text="No servers found - Enter IP manually", 
                text_color=Theme.STATUS_WARNING
            )
    
    def on_server_selected(self, choice):
        """Handle selecting a discovered server."""
        if not self.discovered_servers:
            return
        
        # Look up selected server entry
        for server in self.discovered_servers:
            display_name = f"{server['name']} - {server['ip']}:{server['port']}"
            if display_name == choice:
                self.entry_ip.delete(0, "end")
                self.entry_ip.insert(0, server['ip'])
                self.label_status.configure(
                    text=f"Selected: {server['name']} - Connecting...", 
                    text_color=Theme.STATUS_SUCCESS
                )
                if self.is_running:
                    self.stop_receiving()
                    self.master.after(200, self.start_receiving)
                else:
                    self.master.after(100, self.start_receiving)
                break

    def start_receiving(self):
        if self._connecting or self.is_running:
            return
        self._connecting = True
        self._cancel_connect = False

        self.refresh_driver_status()
        driver_status = self.driver_status
        prefer_custom = driver_status is not None and driver_status.status_code == "ok"

        ip = self.entry_ip.get()
        url = f"http://{ip}:8000/stream.mjpg"

        self.btn_connect.configure(text="Connecting...", state="disabled")
        if prefer_custom:
            self.label_status.configure(text="Connecting...", text_color=Theme.STATUS_WARNING)
        else:
            self.label_status.configure(
                text="Connecting... Custom unavailable, using fallback virtual camera",
                text_color=Theme.STATUS_WARNING,
            )

        def worker():
            client = None
            vcam = None
            start_code = ""
            start_message = ""
            try:
                client = StreamClient(url)
                client.start()

                vcam = VirtualCamera(
                    width=1280,
                    height=720,
                    prefer_custom=prefer_custom,
                    allow_custom_when_mismatch=False,
                )
                _is_custom, start_code, start_message = vcam.start()
            except Exception as e:
                if client:
                    client.stop()
                if vcam:
                    vcam.stop()
                self.master.after(0, lambda: self._on_connect_failed(e))
                return

            self.master.after(
                0,
                lambda: self._on_connect_success(client, vcam, start_code, start_message, driver_status),
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_connect_success(self, client, vcam, start_code="", start_message="", driver_status=None):
        if self._cancel_connect:
            client.stop()
            if vcam:
                vcam.stop()
            self._connecting = False
            self._cancel_connect = False
            self.btn_connect.configure(
                text="Connect",
                fg_color=Theme.ACCENT,
                hover_color=Theme.ACCENT_HOVER,
                state="normal"
            )
            self.label_status.configure(text="Disconnected", text_color=Theme.STATUS_IDLE)
            return

        self.client = client
        self.virtual_cam = vcam
        self.is_running = True
        self._connecting = False
        self.btn_connect.configure(
            text="Disconnect",
            fg_color=Theme.ACCENT_DANGER,
            hover_color=Theme.ACCENT_DANGER_HOVER,
            state="normal"
        )

        if start_code == "fallback_started":
            if driver_status and driver_status.status_code != "ok":
                self.label_status.configure(
                    text="Connected - Using fallback virtual camera (Install to repair custom driver)",
                    text_color=Theme.STATUS_WARNING,
                )
            else:
                self.label_status.configure(
                    text="Connected - Using fallback virtual camera",
                    text_color=Theme.STATUS_WARNING,
                )
        else:
            self.label_status.configure(text="Connected - Streaming", text_color=Theme.STATUS_SUCCESS)

        if start_message:
            print(f"[VirtualCameraStart] {start_message}")

        self.thread = threading.Thread(target=self.process_stream, daemon=True)
        self.thread.start()

    def _on_connect_failed(self, error):
        self._connecting = False
        self._cancel_connect = False
        self.label_status.configure(text=f"Error: {error}", text_color=Theme.STATUS_ERROR)
        self.btn_connect.configure(
            text="Connect",
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            state="normal"
        )

    def stop_receiving(self):
        if self._connecting:
            self._cancel_connect = True
        self.is_running = False
        if self.client:
            self.client.stop()
            self.client = None
        if self.virtual_cam:
            self.virtual_cam.stop()
            self.virtual_cam = None

        self.photo_image = None
        self.btn_connect.configure(
            text="Connect",
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            state="normal"
        )
        self.label_status.configure(text="Disconnected", text_color=Theme.STATUS_IDLE)

        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text="Stream Preview")

    def _ensure_virtual_camera_for_frame(self, frame):
        if not self.is_running or frame is None:
            return False

        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return False

        prefer_custom = self.driver_status is not None and self.driver_status.status_code == "ok"

        if self.virtual_cam is None:
            self.master.after(
                0,
                lambda w=w, h=h: self.label_status.configure(
                    text=f"Starting virtual camera ({w}x{h})...",
                    text_color=Theme.STATUS_WARNING,
                ),
            )
            try:
                vcam = VirtualCamera(
                    width=w,
                    height=h,
                    prefer_custom=prefer_custom,
                    allow_custom_when_mismatch=False,
                )
                _is_custom, start_code, _start_message = vcam.start()
                self.virtual_cam = vcam

                if start_code == "fallback_started" and self.driver_status and self.driver_status.status_code != "ok":
                    status_text = "Connected - Using fallback virtual camera (Install to repair custom driver)"
                    status_color = Theme.STATUS_WARNING
                else:
                    status_text = f"Connected - Streaming ({w}x{h})"
                    status_color = Theme.STATUS_SUCCESS

                self.master.after(
                    0,
                    lambda text=status_text, color=status_color: self.label_status.configure(
                        text=text,
                        text_color=color,
                    ),
                )
                return True
            except Exception as error:
                self.master.after(
                    0,
                    lambda error=error: self.label_status.configure(
                        text=f"Virtual camera start failed: {error}",
                        text_color=Theme.STATUS_ERROR,
                    ),
                )
                return False

        if self.virtual_cam.width == w and self.virtual_cam.height == h:
            return True

        self.master.after(
            0,
            lambda w=w, h=h: self.label_status.configure(
                text=f"Reconfiguring virtual camera ({w}x{h})...",
                text_color=Theme.STATUS_WARNING,
            ),
        )
        try:
            self.virtual_cam.reconfigure(w, h)
            if self.driver_status and self.driver_status.status_code != "ok":
                status_text = "Connected - Using fallback virtual camera (Install to repair custom driver)"
                status_color = Theme.STATUS_WARNING
            else:
                status_text = f"Connected - Streaming ({w}x{h})"
                status_color = Theme.STATUS_SUCCESS
            self.master.after(
                0,
                lambda text=status_text, color=status_color: self.label_status.configure(
                    text=text,
                    text_color=color,
                ),
            )
            return True
        except Exception as error:
            self.master.after(
                0,
                lambda error=error: self.label_status.configure(
                    text=f"Reconfigure failed: {error}",
                    text_color=Theme.STATUS_ERROR,
                ),
            )
            return False

    def process_stream(self):
        if not self.client:
            return

        for frame in self.client.get_frames():
            if not self.is_running:
                break

            if not self._ensure_virtual_camera_for_frame(frame):
                if not self.is_running:
                    break
                time.sleep(self._virtual_cam_retry_sec)
                continue

            if self.virtual_cam and not self.virtual_cam.send_frame(frame):
                time.sleep(self._virtual_cam_retry_sec)
                continue

            # Skip frame if previous frame is still being processed
            if self._pending_frame:
                continue

            # Skip preview work when disabled/minimized
            if not self.preview_enabled or self._is_minimized():
                if not self.preview_enabled:
                    self.master.after(0, lambda: self._show_preview_message("Preview Disabled"))
                else:
                    self.master.after(0, lambda: self._show_preview_message("Minimized (Preview Paused)"))
                time.sleep(0.1)
                continue
            
            # Process image in background thread for performance
            try:
                canvas_width, canvas_height = self._canvas_size
                if canvas_width < 10:
                    canvas_width = 640
                if canvas_height < 10:
                    canvas_height = 360
                
                h, w = frame.shape[:2]
                ratio = min(canvas_width / w, canvas_height / h)
                preview_width = max(1, int(w * ratio))
                preview_height = max(1, int(h * ratio))
                frame_resized = cv2.resize(frame, (preview_width, preview_height))
                
                # Convert to RGB
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                
                self._pending_frame = True
                # Update Preview (run on main thread) - only PIL conversion and drawing
                self.master.after(0, self._draw_preview, frame_rgb, canvas_width, canvas_height)
            except Exception as e:
                print(f"Preview processing error: {e}")

    def _draw_preview(self, frame_rgb, canvas_width, canvas_height):
        """Draw pre-processed frame on canvas (runs on main thread)."""
        if not self.is_running:
            self._pending_frame = False
            return
        
        try:
            # Convert to PIL Image and PhotoImage (lightweight operations)
            image = Image.fromarray(frame_rgb)
            self.photo_image = ImageTk.PhotoImage(image)
            
            # Draw on canvas
            self.preview_canvas.delete("preview")
            self.preview_canvas.itemconfig(self.preview_text, text="")
            x = canvas_width // 2
            y = canvas_height // 2
            self.preview_canvas.create_image(x, y, image=self.photo_image, tag="preview")
        except Exception as e:
            print(f"Preview error: {e}")
        finally:
            self._pending_frame = False

    def toggle_preview(self):
        """Toggle preview visibility."""
        self.preview_enabled = not self.preview_enabled
        if self.preview_enabled:
            self.btn_preview_toggle.configure(text="👁", text_color=Theme.ACCENT)
        else:
            self.btn_preview_toggle.configure(text="X", text_color=Theme.TEXT_SECONDARY)
            self._show_preview_message("Preview Disabled")
    
    def _is_minimized(self):
        """Return whether the window is minimized."""
        try:
            return self.master.state() == "iconic"
        except Exception:
            return False

    def _show_preview_message(self, message):
        """Show a message in the preview area."""
        self.preview_canvas.delete("preview")
        self.preview_canvas.itemconfig(self.preview_text, text=message)

    def _on_back(self):
        """Handle back button click."""
        if self.on_back:
            self.on_back()

    def cleanup(self):
        """Clean up resources before destroying."""
        self.stop_receiving()



