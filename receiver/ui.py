import customtkinter as ctk
import cv2
import threading
from PIL import Image, ImageTk
from .client import StreamClient
from .virtual_cam import VirtualCamera
from utils.network import ServerDiscovery
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
        self.discovered_servers = []  # 検出されたサーバーリスト
        self._pending_frame = False  # フレーム処理中フラグ（スキップ用）
        self._canvas_size = (640, 360)  # キャンバスサイズのキャッシュ

        self.setup_ui()

    def setup_ui(self):
        # Title
        self.label_title = ctk.CTkLabel(self, text="Virtual Camera Receiver", font=("Arial", 20, "bold"))
        self.label_title.pack(pady=10)

        # Controls - Row 1: Auto-discovery
        self.frame_discovery = ctk.CTkFrame(self)
        self.frame_discovery.pack(pady=5)

        self.btn_discover = ctk.CTkButton(
            self.frame_discovery, 
            text="🔍 サーバー自動検出", 
            command=self.discover_servers,
            width=160
        )
        self.btn_discover.pack(side="left", padx=5)

        self.server_dropdown = ctk.CTkComboBox(
            self.frame_discovery,
            values=["検出されたサーバーがありません"],
            width=250,
            state="readonly",
            command=self.on_server_selected
        )
        self.server_dropdown.pack(side="left", padx=5)

        # Controls - Row 2: Manual IP input
        self.frame_controls = ctk.CTkFrame(self)
        self.frame_controls.pack(pady=5)

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
        self._canvas_size = (event.width, event.height)

    def toggle_connection(self):
        if not self.is_running:
            self.start_receiving()
        else:
            self.stop_receiving()

    def discover_servers(self):
        """LANでサーバーを自動検出"""
        self.btn_discover.configure(state="disabled", text="🔍 検索中...")
        self.label_status.configure(text="サーバーを検索中...", text_color="yellow")
        
        def search():
            discovery = ServerDiscovery(timeout=3.0)
            servers = discovery.discover()
            self.master.after(0, lambda: self.update_server_list(servers))
        
        threading.Thread(target=search, daemon=True).start()
    
    def update_server_list(self, servers):
        """検出結果をUIに反映"""
        self.btn_discover.configure(state="normal", text="🔍 サーバー自動検出")
        self.discovered_servers = servers
        
        if servers:
            # サーバーが見つかった
            server_names = [f"{s['name']} - {s['ip']}:{s['port']}" for s in servers]
            self.server_dropdown.configure(values=server_names)
            self.server_dropdown.set(server_names[0])
            
            # 単一サーバーの場合は自動でIPを入力
            if len(servers) == 1:
                self.entry_ip.delete(0, "end")
                self.entry_ip.insert(0, servers[0]['ip'])
                self.label_status.configure(
                    text=f"✓ サーバー検出: {servers[0]['name']}", 
                    text_color="green"
                )
            else:
                self.label_status.configure(
                    text=f"✓ {len(servers)}台のサーバーを検出 - ドロップダウンから選択", 
                    text_color="green"
                )
        else:
            # サーバーが見つからなかった
            self.server_dropdown.configure(values=["検出されたサーバーがありません"])
            self.server_dropdown.set("検出されたサーバーがありません")
            self.label_status.configure(
                text="サーバーが見つかりません - 手動でIPを入力してください", 
                text_color="orange"
            )
    
    def on_server_selected(self, choice):
        """ドロップダウンでサーバー選択時にIPを入力欄に反映"""
        if not self.discovered_servers:
            return
        
        # 選択されたサーバーを検索
        for server in self.discovered_servers:
            display_name = f"{server['name']} - {server['ip']}:{server['port']}"
            if display_name == choice:
                self.entry_ip.delete(0, "end")
                self.entry_ip.insert(0, server['ip'])
                self.label_status.configure(
                    text=f"選択: {server['name']}", 
                    text_color="green"
                )
                break

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

            # Skip frame if previous frame is still being processed
            if self._pending_frame:
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
                preview_width = int(w * ratio)
                preview_height = int(h * ratio)
                frame_resized = cv2.resize(frame, (preview_width, preview_height))
                
                # Convert to RGB
                frame_rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
                
                self._pending_frame = True
                # Update Preview (run on main thread) - only PIL conversion and drawing
                self.master.after(0, self._draw_preview, frame_rgb, canvas_width, canvas_height)
            except Exception as e:
                print(f"Preview processing error: {e}")

    def _draw_preview(self, frame_rgb, canvas_width, canvas_height):
        """Draw pre-processed frame on canvas (runs on main thread)"""
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
