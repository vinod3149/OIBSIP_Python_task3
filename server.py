import socket
import threading
import json

HOST = '127.0.0.1'
PORT = 9090

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen()
print(f"Server is listening on {HOST}:{PORT}")

clients = {} # {username: {"socket": client_socket, "public_key": public_key_pem}}

def broadcast(payload):
    """Encodes a payload to JSON and sends it to all clients."""
    message = json.dumps(payload) + "\n"
    for client_info in list(clients.values()):
        try:
            client_info["socket"].sendall(message.encode('utf-8'))
        except Exception as e:
            print(f"Error broadcasting: {e}")

def handle_client(client_socket, client_address):
    username = ""
    buffer = ""
    try:
        # The first message must be a login payload
        initial_data = client_socket.recv(4096).decode('utf-8')
        payload = json.loads(initial_data)

        if payload.get("type") == "login":
            username = payload["username"]
            if username in clients:
                error_payload = {"type": "error", "message": "Username is already taken."}
                client_socket.sendall((json.dumps(error_payload) + "\n").encode('utf-8'))
                return # End thread
            
            clients[username] = {"socket": client_socket, "public_key": payload["public_key"]}
            print(f"Registered: {username}")
            broadcast({"type": "userlist", "users": list(clients.keys())})
        else:
            # If the first message isn't login, disconnect
            return

        # Main loop for receiving further messages
        while True:
            data = client_socket.recv(8192).decode('utf-8')
            if not data: break
            
            buffer += data
            while "\n" in buffer:
                message_json, buffer = buffer.split("\n", 1)
                payload = json.loads(message_json)
                msg_type = payload.get("type")
                recipient = payload.get("recipient")

                # Add sender to the payload for easy forwarding
                payload["sender"] = username

                if msg_type == "get_key":
                    if recipient in clients:
                        key_payload = {"type": "key_response", "username": recipient, "public_key": clients[recipient]["public_key"]}
                        client_socket.sendall((json.dumps(key_payload) + "\n").encode('utf-8'))
                
                elif recipient in clients:
                    # Forward any other message with a recipient
                    clients[recipient]["socket"].sendall((json.dumps(payload) + "\n").encode('utf-8'))
    
    except (ConnectionResetError, json.JSONDecodeError):
        # Handle clients disconnecting unexpectedly
        pass
    except Exception as e:
        print(f"An error occurred with {username}: {e}")
    finally:
        if username in clients:
            del clients[username]
            print(f"Unregistered {username}.")
            broadcast({"type": "userlist", "users": list(clients.keys())})
        client_socket.close()

while True:
    client_socket, client_address = server.accept()
    threading.Thread(target=handle_client, args=(client_socket, client_address), daemon=True).start()
