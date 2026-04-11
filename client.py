import customtkinter as ctk
import tkinter
from tkinter import messagebox, filedialog
import socket
import threading
import json
import base64
import os
import io
from crypto_utils import ensure_keys_exist, load_keys, encrypt_message, decrypt_message
from cryptography.hazmat.primitives import serialization
from PIL import Image
from database import initialize_database, save_message, load_messages

class ChatClient(ctk.CTk):
    def __init__(self, host, port):
        super().__init__()
        
        self.host, self.port, self.username, self.current_chat_partner, self.client_socket = host, port, "", None, None
        self.partner_public_keys, self.online_users, self.unread_messages = {}, [], set()
        self.private_key, self.public_key = None, None
        self.load_or_generate_keys()
        initialize_database()

        ctk.set_appearance_mode("light")
        self.title("Secure Chat"), self.geometry("800x600")
        self.grid_rowconfigure(0, weight=1), self.grid_columnconfigure(1, weight=1)

        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color="#5DADE2")
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew"), self.sidebar_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self.sidebar_frame, text="Online Users", text_color="black", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, padx=20, pady=10)
        self.user_listbox = tkinter.Listbox(self.sidebar_frame, font=("Helvetica", 14), bg="#AED6F1", fg="black", selectbackground="#3498DB", borderwidth=0, highlightthickness=0, activestyle="none")
        self.user_listbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        self.user_listbox.bind("<<ListboxSelect>>", self.on_user_select)

        self.chat_frame = ctk.CTkFrame(self, fg_color="#D6EAF8")
        self.chat_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.chat_frame.grid_rowconfigure(1, weight=1), self.chat_frame.grid_columnconfigure(0, weight=1)
        self.chat_partner_label = ctk.CTkLabel(self.chat_frame, text="Select a user to start chatting", text_color="black", font=ctk.CTkFont(size=18, weight="bold"))
        self.chat_partner_label.grid(row=0, column=0, columnspan=4, pady=10, sticky="ew")
        self.chat_display = ctk.CTkScrollableFrame(self.chat_frame, fg_color="white")
        self.chat_display.grid(row=1, column=0, sticky="nsew", columnspan=4), self.chat_display.grid_columnconfigure((0, 1), weight=1)
        self.message_entry = ctk.CTkEntry(self.chat_frame, placeholder_text="Type your message...", text_color="black", fg_color="white")
        self.message_entry.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.message_entry.bind("<Return>", self.send_message)
        
        attach_button = ctk.CTkButton(self.chat_frame, text="📎", width=35, height=35, font=ctk.CTkFont(size=20), command=self.attach_file)
        attach_button.grid(row=2, column=1, pady=(10,0), padx=5)
        emoji_button = ctk.CTkButton(self.chat_frame, text="😊", width=35, height=35, font=ctk.CTkFont(size=20), command=self.open_emoji_picker)
        emoji_button.grid(row=2, column=2, pady=(10,0), padx=5)
        self.send_button = ctk.CTkButton(self.chat_frame, text="Send", width=80, command=self.send_message)
        self.send_button.grid(row=2, column=3, sticky="e", pady=(10, 0), padx=(10, 0))
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(100, self.connect_to_server)

    def load_or_generate_keys(self):
        ensure_keys_exist(); self.private_key, self.public_key = load_keys()

    def send_json(self, payload):
        try: self.client_socket.sendall((json.dumps(payload) + "\n").encode('utf-8'))
        except: self.add_message_bubble("System: Connection error", "left")

    def connect_to_server(self):
        dialog = ctk.CTkInputDialog(text="Enter your username:", title="Login")
        self.username = dialog.get_input()
        if not self.username: self.destroy(); return
        self.title(f"Chat - {self.username}")
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((self.host, self.port))
            public_key_pem = self.public_key.public_bytes(encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo).decode('utf-8')
            login_payload = {"type": "login", "username": self.username, "public_key": public_key_pem}
            self.client_socket.sendall((json.dumps(login_payload) + "\n").encode('utf-8'))
            threading.Thread(target=self.receive_messages, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {e}"); self.destroy()

    def receive_messages(self):
        buffer = ""
        while True:
            try:
                data = self.client_socket.recv(8192).decode('utf-8')
                if not data: break
                buffer += data
                while "\n" in buffer:
                    message_json, buffer = buffer.split("\n", 1)
                    payload = json.loads(message_json)
                    msg_type, sender = payload.get("type"), payload.get("sender")
                    
                    if msg_type == "userlist": self.after(0, self.update_user_list, payload["users"])
                    elif msg_type == "key_response":
                        self.partner_public_keys[payload["username"]] = payload["public_key"].encode('utf-8')
                        self.after(0, self.add_message_bubble, f"System: Key for {payload['username']} received.", "left")
                    elif msg_type == "private_message":
                        encrypted_content = base64.b64decode(payload["content"].encode('utf-8'))
                        decrypted_message = decrypt_message(self.private_key, encrypted_content)
                        
                        # --- THIS IS THE FIX ---
                        # The receiver should NOT save the message. Only the sender does.
                        # save_message(sender, self.username, decrypted_message) <-- DELETED

                        if sender == self.current_chat_partner: self.after(0, self.add_message_bubble, decrypted_message, "left")
                        else: self.unread_messages.add(sender); self.after(0, self.update_user_list, self.online_users)
                    elif msg_type == "file_transfer":
                        file_data = base64.b64decode(payload["file_data"])
                        
                        # The receiver should NOT save the file. Only the sender does.
                        # save_message(sender, self.username, image_data=file_data) <-- DELETED
                        
                        if sender == self.current_chat_partner: self.after(0, self.add_image_bubble, file_data, "left")
                        else: self.unread_messages.add(sender); self.after(0, self.update_user_list, self.online_users)
                    elif msg_type == "error":
                        self.after(0, messagebox.showerror, "Server Error", payload["message"])
                        if "Username" in payload["message"]: self.after(10, self.destroy)
            except: break
        self.client_socket.close()
    
    def send_message(self, event=None):
        message_content = self.message_entry.get()
        if not (message_content and self.current_chat_partner): return
        recipient = self.current_chat_partner
        if recipient not in self.partner_public_keys:
            self.send_json({"type": "get_key", "recipient": recipient}); return
        try:
            partner_key_pem = self.partner_public_keys[recipient]
            encrypted_message = encrypt_message(partner_key_pem, message_content)
            encrypted_b64 = base64.b64encode(encrypted_message).decode('utf-8')
            self.send_json({"type": "private_message", "recipient": recipient, "content": encrypted_b64})
            save_message(self.username, recipient, message_content)
            self.add_message_bubble(message_content, "right")
            self.message_entry.delete(0, 'end')
        except Exception as e:
            self.add_message_bubble(f"System: Error sending. {e}", "left")
    
    def attach_file(self):
        if not self.current_chat_partner:
            messagebox.showwarning("No Recipient", "Please select a user to send a file to.")
            return
        filepath = filedialog.askopenfilename(title="Select an image", filetypes=(("Image files", "*.jpg *.jpeg *.png *.gif"),))
        if not filepath: return
        try:
            with open(filepath, "rb") as f: file_data = f.read()
            file_b64 = base64.b64encode(file_data).decode('utf-8')
            filename = os.path.basename(filepath)
            payload = {"type": "file_transfer", "recipient": self.current_chat_partner, "filename": filename, "file_data": file_b64}
            self.send_json(payload)
            save_message(self.username, self.current_chat_partner, image_data=file_data)
            self.add_image_bubble(file_data, "right")
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to send file: {e}")

    def update_user_list(self, online_users):
        self.online_users = online_users
        self.user_listbox.delete(0, tkinter.END)
        other_users = sorted([user for user in self.online_users if user and user != self.username])
        self.user_listbox.insert(tkinter.END, f"{self.username} (You)")
        self.user_listbox.itemconfig(0, {'fg': '#000080'})
        for user in other_users:
            self.user_listbox.insert(tkinter.END, f"● {user}" if user in self.unread_messages else user)
    
    def on_user_select(self, event):
        indices = event.widget.curselection()
        if not indices: return
        index = indices[0]
        if index == 0: event.widget.selection_clear(0, tkinter.END); return
        selected_user = event.widget.get(index).replace("● ", "").strip()
        self.switch_chat(selected_user)

    def switch_chat(self, partner_name):
        # --- THIS IS THE FIX ---
        # If the user clicks on the person they are already chatting with, do nothing.
        if partner_name == self.current_chat_partner:
            return

        self.current_chat_partner = partner_name
        self.chat_partner_label.configure(text=f"Chat with {partner_name}")
        self.message_entry.configure(placeholder_text=f"Message {partner_name}...")
        
        if partner_name in self.unread_messages:
            self.unread_messages.remove(partner_name)
            self.update_user_list(self.online_users)
        
        # Clear the chat display for the new user
        for widget in self.chat_display.winfo_children():
            widget.destroy()
            
        # Load the history for the new user
        history = load_messages(self.username, partner_name)
        for sender, message, image_data in history:
            align = "right" if sender == self.username else "left"
            if image_data:
                self.add_image_bubble(image_data, align)
            elif message:
                self.add_message_bubble(message, align)

        if partner_name not in self.partner_public_keys:
            self.send_json({"type": "get_key", "recipient": partner_name})

    def add_message_bubble(self, message, align):
        bubble_frame = ctk.CTkFrame(self.chat_display, fg_color="transparent")
        if align == "right": bubble_frame.grid(row=len(self.chat_display.winfo_children()), column=1, sticky="e", padx=(50, 5), pady=2)
        else: bubble_frame.grid(row=len(self.chat_display.winfo_children()), column=0, sticky="w", padx=(5, 50), pady=2)
        label = ctk.CTkLabel(bubble_frame, text=message, wraplength=350, fg_color=("#007BFF" if align=="right" else "#E0E0E0"), text_color=("white" if align=="right" else "black"), corner_radius=15, justify=("right" if align=="right" else "left"), padx=10, pady=5)
        label.pack()
        self.after(50, self._scroll_to_bottom)

    def add_image_bubble(self, image_data, align):
        try:
            image = Image.open(io.BytesIO(image_data))
            image.thumbnail((200, 200))
            ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            bubble_frame = ctk.CTkFrame(self.chat_display, fg_color="transparent")
            if align == "right": bubble_frame.grid(row=len(self.chat_display.winfo_children()), column=1, sticky="e", padx=(50, 5), pady=2)
            else: bubble_frame.grid(row=len(self.chat_display.winfo_children()), column=0, sticky="w", padx=(5, 50), pady=2)
            image_label = ctk.CTkLabel(bubble_frame, text="", image=ctk_image)
            image_label.pack()
            self.after(50, self._scroll_to_bottom)
        except: self.add_message_bubble("[Image failed to load]", align)

    def open_emoji_picker(self):
        emoji_window = ctk.CTkToplevel(self)
        emoji_window.title("Select an Emoji"), emoji_window.geometry("400x300")
        emoji_window.resizable(False, False), emoji_window.grab_set()
        tab_view = ctk.CTkTabview(emoji_window, width=400, height=300)
        tab_view.pack(expand=True, fill="both")
        emojis = { "Smileys": ['😊', '😂', '😍', '🤔', '👍', '❤️', '🎉', '🔥', '👋', '😢', '🙏', '💯'], "Animals": ['🐶', '🐱', '🐭', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯', '🦁', '🐮', '🐷'],"Food": ['🍎', '🍌', '🍉', '🍇', '🍓', '🍑', '🍍', '🍕', '🍔', '🍟', '🍿', '🍩']}
        for category, emoji_list in emojis.items():
            tab = tab_view.add(category)
            scroll_frame = ctk.CTkScrollableFrame(tab, fg_color="transparent")
            scroll_frame.pack(expand=True, fill="both")
            row, col = 0, 0
            for emoji in emoji_list:
                emoji_button = ctk.CTkButton(scroll_frame, text=emoji, width=40, height=40, font=ctk.CTkFont(size=20), command=lambda e=emoji, w=emoji_window: self.insert_emoji(e, w))
                emoji_button.grid(row=row, column=col, padx=5, pady=5)
                col += 1
                if col > 5: col = 0; row += 1

    def insert_emoji(self, emoji, emoji_window):
        self.message_entry.insert('end', emoji); emoji_window.destroy()
        
    def _scroll_to_bottom(self):
        self.chat_display._parent_canvas.yview_moveto(1.0)
        
    def on_closing(self):
        try: self.client_socket.close()
        except: pass
        self.destroy()

if __name__ == "__main__":
    app = ChatClient('127.0.0.1', 9090)
    app.mainloop()
