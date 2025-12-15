import socket
import threading
import json
import time
import random
import string
import os
import logging

TCP_PORT = 50000
DISCOVERY_PORT = 50001

def room_code():
    return ''.join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))

# Module logger
logger = logging.getLogger("multiplayer_server")
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class RoomServer:
    def __init__(self):
        self.code = room_code()
        self.clients = {}  # conn -> {"id": str, "x": int, "y": int}
        self.running = True

    def start(self):
        logger.info("Room created. Code: %s", self.code)
        # write room code to a file so local hosts can read it
        try:
            path = os.path.join(os.path.dirname(__file__), "room_code.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.code)
        except Exception:
            logger.debug("Failed to write room code file", exc_info=True)
        threading.Thread(target=self.discovery_loop, daemon=True).start()
        threading.Thread(target=self.tcp_loop, daemon=True).start()
        self.game_loop()

    # UDP discovery
    def discovery_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", DISCOVERY_PORT))

        while self.running:
            try:
                msg, addr = sock.recvfrom(1024)
                if msg.decode() == "DISCOVER_ROOM":
                    logger.debug("Discovery request from %s", addr)
                    reply = {
                        "type": "room",
                        "room_code": self.code,
                        "host": socket.gethostbyname(socket.gethostname()),
                        "tcp_port": TCP_PORT,
                    }
                    sock.sendto(json.dumps(reply).encode(), addr)
            except Exception:
                logger.debug("Error in discovery loop", exc_info=True)

    # TCP accept
    def tcp_loop(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("", TCP_PORT))
        srv.listen(8)

        while self.running:
            try:
                conn, addr = srv.accept()
                pid = f"P{len(self.clients)+1}"
                self.clients[conn] = {"id": pid, "x": 500, "y": 350}

                logger.info("Accepted connection %s as %s", addr, pid)
                conn.sendall(json.dumps({"type": "welcome", "id": pid}).encode()+b"\n")
                threading.Thread(target=self.client_receiver, args=(conn,), daemon=True).start()
            except Exception:
                logger.debug("Error accepting connection", exc_info=True)

    # TCP receive loop
    def client_receiver(self, conn):
        buf = b""
        while self.running:
            try:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line.decode())

                    # update only x,y
                    player = self.clients.get(conn)
                    if player:
                        player["x"] += msg.get("dx", 0)
                        player["y"] += msg.get("dy", 0)

            except Exception:
                break

        player = self.clients.pop(conn, None)
        if player:
            logger.info("Client %s disconnected", player.get("id"))
        try:
            conn.close()
        except Exception:
            logger.debug("Error closing connection", exc_info=True)

    # Broadcast loop
    def game_loop(self):
        while self.running:
            state = {
                "type": "state",
                "players": list(self.clients.values())
            }
            data = json.dumps(state).encode() + b"\n"

            for conn in list(self.clients.keys()):
                try:
                    conn.sendall(data)
                except Exception as e:
                    player = self.clients.pop(conn, None)
                    if player:
                        logger.info("Removed client %s due to send error: %s", player.get("id"), e)
                    try:
                        conn.close()
                    except Exception:
                        logger.debug("Error closing connection after send failure", exc_info=True)

            time.sleep(1/20)

if __name__ == "__main__":
    RoomServer().start()
