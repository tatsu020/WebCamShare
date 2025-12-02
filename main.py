import customtkinter as ctk
from sender.ui import SenderApp
from receiver.ui import ReceiverApp

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class MainApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Webcam Share & Virtual Cam")
        self.geometry("800x600")

        self.frame_menu = ctk.CTkFrame(self)
        self.frame_menu.pack(pady=20, padx=20, fill="both", expand=True)

        self.label_intro = ctk.CTkLabel(self.frame_menu, text="Choose Mode", font=("Arial", 24, "bold"))
        self.label_intro.pack(pady=20)

        self.btn_sender = ctk.CTkButton(self.frame_menu, text="Sender (Camera Host)", command=self.start_sender, height=50, font=("Arial", 16))
        self.btn_sender.pack(pady=10, fill="x", padx=50)

        self.btn_receiver = ctk.CTkButton(self.frame_menu, text="Receiver (Virtual Camera)", command=self.start_receiver, height=50, font=("Arial", 16))
        self.btn_receiver.pack(pady=10, fill="x", padx=50)

    def start_sender(self):
        self.frame_menu.pack_forget()
        self.sender_app = SenderApp(self)

    def start_receiver(self):
        self.frame_menu.pack_forget()
        self.receiver_app = ReceiverApp(self)

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
