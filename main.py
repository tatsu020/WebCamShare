import customtkinter as ctk
import sys
from pathlib import Path
import ctypes
import tkinter as tk
from sender.ui import SenderApp
from receiver.ui import ReceiverApp
from utils.theme import Theme

ctk.set_appearance_mode("Dark")

APP_USER_MODEL_ID = "tatsu020.WebCamShare"

def set_windows_app_user_model_id(app_id: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass

def find_resource(filename: str) -> Path | None:
    nuitka_dir = None
    try:
        import __compiled__  # type: ignore
        nuitka_dir = Path(getattr(__compiled__, "containing_dir", ""))
    except Exception:
        nuitka_dir = None

    candidates = [
        nuitka_dir / filename if nuitka_dir else None,
        Path(getattr(sys, "_MEIPASS", "")) / filename,
        Path(__file__).resolve().parent / filename,
        Path(sys.argv[0]).resolve().parent / filename,
        Path.cwd() / filename,
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    return None

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WebCam Share")
        self.geometry("800x680")
        self.configure(fg_color=Theme.BG_DARK)
        self.after(0, self.apply_app_icon)

        # Main container with centered content
        self.frame_menu = ctk.CTkFrame(
            self, 
            fg_color=Theme.BG_CARD,
            corner_radius=Theme.RADIUS_LG
        )
        self.frame_menu.pack(pady=Theme.PAD_XL, padx=Theme.PAD_XL, fill="both", expand=True)

        # Spacer for vertical centering
        self.frame_menu.grid_rowconfigure(0, weight=1)
        self.frame_menu.grid_rowconfigure(4, weight=1)
        self.frame_menu.grid_columnconfigure(0, weight=1)

        # App title
        self.label_title = ctk.CTkLabel(
            self.frame_menu, 
            text="WebCam Share", 
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_PRIMARY
        )
        self.label_title.grid(row=1, column=0, pady=(Theme.PAD_XL, Theme.PAD_SM))

        # Subtitle
        self.label_subtitle = ctk.CTkLabel(
            self.frame_menu, 
            text="Stream your camera or receive as virtual device", 
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_SECONDARY
        )
        self.label_subtitle.grid(row=2, column=0, pady=(0, Theme.PAD_LG))

        # Button container
        self.frame_buttons = ctk.CTkFrame(self.frame_menu, fg_color="transparent")
        self.frame_buttons.grid(row=3, column=0, pady=Theme.PAD_MD)

        # Sender button
        self.btn_sender = ctk.CTkButton(
            self.frame_buttons, 
            text="📷  Sender Mode", 
            command=self.start_sender, 
            height=56,
            width=280,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.ACCENT,
            hover_color=Theme.ACCENT_HOVER,
            corner_radius=Theme.RADIUS_MD
        )
        self.btn_sender.pack(pady=Theme.PAD_SM)

        # Receiver button
        self.btn_receiver = ctk.CTkButton(
            self.frame_buttons, 
            text="🖥️  Receiver Mode", 
            command=self.start_receiver, 
            height=56,
            width=280,
            font=Theme.FONT_BUTTON,
            fg_color=Theme.BG_INPUT,
            hover_color="#2d2d3d",
            border_width=2,
            border_color=Theme.ACCENT,
            corner_radius=Theme.RADIUS_MD
        )
        self.btn_receiver.pack(pady=Theme.PAD_SM)

    def apply_app_icon(self):
        """Ensure window and taskbar icons use the app icon on Windows."""
        icon_ico = find_resource("icon.ico")
        icon_png = find_resource("icon.png")
        if sys.platform == "win32" and icon_ico:
            try:
                self.iconbitmap(str(icon_ico))
                self.iconbitmap(default=str(icon_ico))
            except Exception:
                pass
        if icon_png:
            try:
                self._app_icon_image = tk.PhotoImage(file=str(icon_png))
                self.iconphoto(True, self._app_icon_image)
            except Exception:
                try:
                    from PIL import Image, ImageTk
                    image = Image.open(icon_png)
                    self._app_icon_image = ImageTk.PhotoImage(image)
                    self.iconphoto(True, self._app_icon_image)
                except Exception:
                    pass

    def start_sender(self):
        self.frame_menu.pack_forget()
        self.sender_app = SenderApp(self, on_back=self.show_menu)

    def start_receiver(self):
        self.frame_menu.pack_forget()
        self.receiver_app = ReceiverApp(self, on_back=self.show_menu)

    def show_menu(self):
        """Return to main menu"""
        # Clean up current app
        if hasattr(self, 'sender_app') and self.sender_app:
            self.sender_app.cleanup()
            self.sender_app.pack_forget()
            self.sender_app.destroy()
            self.sender_app = None
        if hasattr(self, 'receiver_app') and self.receiver_app:
            self.receiver_app.cleanup()
            self.receiver_app.pack_forget()
            self.receiver_app.destroy()
            self.receiver_app = None
        
        # Show menu
        self.frame_menu.pack(pady=Theme.PAD_XL, padx=Theme.PAD_XL, fill="both", expand=True)

if __name__ == "__main__":
    set_windows_app_user_model_id(APP_USER_MODEL_ID)
    app = MainApp()
    app.mainloop()
