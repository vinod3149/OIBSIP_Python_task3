import sqlite3

def initialize_database():
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            message TEXT,
            image_data BLOB,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_message(sender, recipient, message=None, image_data=None):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (sender, recipient, message, image_data) VALUES (?, ?, ?, ?)",
                   (sender, recipient, message, image_data))
    conn.commit()
    conn.close()

def load_messages(user1, user2):
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    # --- THIS IS THE CORRECTED SQL QUERY ---
    cursor.execute("""
        SELECT sender, message, image_data FROM messages 
        WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)
        ORDER BY timestamp ASC
    """, (user1, user2, user2, user1))
    messages = cursor.fetchall()
    conn.close()
    return messages
