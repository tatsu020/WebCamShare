import customtkinter as ctk
from sender.ui import SenderApp
from receiver.ui import ReceiverApp
from utils.theme import Theme

ctk.set_appearance_mode("Dark")

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("WebCam Share")
        self.geometry("800x600")
        self.configure(fg_color=Theme.BG_DARK)

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
    app = MainApp()
    app.mainloop()
