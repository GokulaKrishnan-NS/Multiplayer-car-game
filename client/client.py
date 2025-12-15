import socket
import threading
import json
import pygame
import time
import os
import subprocess
import sys

DISCOVERY_PORT = 50001
TCP_PORT = 50000

# Discover rooms
def discover_rooms(timeout=1.5):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.4)

    found = []
    start = time.time()

    while time.time() - start < timeout:
        sock.sendto(b"DISCOVER_ROOM", ("<broadcast>", DISCOVERY_PORT))
        try:
            data, addr = sock.recvfrom(1024)
            info = json.loads(data.decode())
            found.append(info)
        except:
            pass

    return found

class Client:
    def __init__(self):
        self.sock = None
        self.players = []
        self.running = True

    def connect(self, host):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, TCP_PORT))
        threading.Thread(target=self.recv_loop, daemon=True).start()

    def recv_loop(self):
        buf = b""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    msg = json.loads(line.decode())
                    if msg["type"] == "welcome":
                        self.id = msg["id"]
                    elif msg["type"] == "state":
                        self.players = msg["players"]
            except:
                break

    def send_input(self, dx, dy):
        msg = json.dumps({"dx": dx, "dy": dy}) + "\n"
        try:
            self.sock.sendall(msg.encode())
        except:
            pass

# ---------------------- PYGAME LOOP ----------------------
pygame.init()
screen = pygame.display.set_mode((1000, 700))
clock = pygame.time.Clock()

def draw_text(surface, text, pos, size=28, color=(255,255,255)):
    font = pygame.font.Font(None, size)
    s = font.render(text, True, color)
    rect = s.get_rect(center=pos)
    surface.blit(s, rect)

def show_menu(screen):
    w, h = screen.get_size()
    join_btn = pygame.Rect(w//2-120, h//2-40, 240, 50)
    create_btn = pygame.Rect(w//2-120, h//2+30, 240, 50)
    message = ""
    server_proc = None
    server_failed = False

    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return None, server_proc
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                mx, my = e.pos
                if join_btn.collidepoint((mx, my)):
                    message = "Searching for rooms..."
                    pygame.display.flip()
                    rooms = discover_rooms()
                    if rooms:
                        return ("join", rooms[0]["host"]), server_proc
                    else:
                        message = "No rooms found. Try Create Room or retry."
                if create_btn.collidepoint((mx, my)):
                    # Launch a fresh local server and connect to localhost
                    # terminate any previous server subprocess we started
                    if server_proc is not None:
                        try:
                            server_proc.terminate()
                        except Exception:
                            pass
                        server_proc = None

                    srv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "server", "server.py"))
                    try:
                        server_proc = subprocess.Popen([sys.executable, srv_path], cwd=os.path.dirname(os.path.dirname(__file__)))
                        server_failed = False
                    except Exception as exc:
                        message = f"Failed to start server: {exc}"
                        server_proc = None
                        server_failed = True
                        continue

                    # wait a short while for the server to start and write the room_code file
                    time.sleep(0.2)
                    return ("create", "127.0.0.1"), server_proc

        screen.fill((30,30,30))
        pygame.draw.rect(screen, (70,70,70), join_btn)
        pygame.draw.rect(screen, (70,70,70), create_btn)
        draw_text(screen, "Join Room", join_btn.center)
        draw_text(screen, "Create Room", create_btn.center)
        if message:
            msg_color = (255,100,100) if server_failed else (200,200,100)
            draw_text(screen, message, (screen.get_width()//2, h//2+110), size=20, color=msg_color)
        pygame.display.flip()
        clock.tick(30)

client = Client()

# Show home screen until user chooses an action
selection, server_proc = show_menu(screen)
if selection is None:
    pygame.quit()
    sys.exit(0)

action, host = selection
if action == "join":
    client.connect(host)
elif action == "create":
    # connect to localhost (server started)
    # try to read room code file written by the server so we can show it to the host
    room_code_display = None
    srv_code_path = os.path.join(os.path.dirname(__file__), "..", "server", "room_code.txt")
    # wait briefly for server to write the file
    for _ in range(20):
        try:
            with open(srv_code_path, "r", encoding="utf-8") as f:
                room_code_display = f.read().strip()
            if room_code_display:
                break
        except Exception:
            pass
        time.sleep(0.1)

    client.connect(host)

    # show waiting screen for host until another player joins
    waiting_start = time.time()
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                client.running = False
                if 'server_proc' in globals() and server_proc:
                    try:
                        server_proc.terminate()
                    except Exception:
                        pass
                sys.exit(0)

        screen.fill((30,30,30))
        title = f"Room Code: {room_code_display or '----'}"
        draw_text(screen, title, (screen.get_width()//2, screen.get_height()//2 - 40), size=36)
        draw_text(screen, "Waiting for players...", (screen.get_width()//2, screen.get_height()//2 + 10), size=28)
        pygame.display.flip()

        # proceed once at least 2 players (host + someone) are present
        if len(client.players) >= 2:
            break

        # safety timeout (optional) 60s
        if time.time() - waiting_start > 60:
            # continue anyway after timeout
            break

        clock.tick(10)

running = True
while running:
    dx = dy = 0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]: dx = -5
    if keys[pygame.K_RIGHT]: dx = 5
    if keys[pygame.K_UP]: dy = -5
    if keys[pygame.K_DOWN]: dy = 5

    client.send_input(dx, dy)

    # draw
    screen.fill((30, 30, 30))
    for p in client.players:
        pygame.draw.rect(screen, (0,255,0), (p["x"], p["y"], 40, 40))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
client.running = False
if 'server_proc' in globals() and server_proc:
    try:
        server_proc.terminate()
    except Exception:
        pass
