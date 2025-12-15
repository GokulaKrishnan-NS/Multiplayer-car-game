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


def draw_text(surface, text, pos, size=28, color=(255,255,255), center=True):
    font = pygame.font.Font(None, size)
    s = font.render(text, True, color)
    if center:
        rect = s.get_rect(center=pos)
    else:
        rect = s.get_rect(topleft=pos)
    surface.blit(s, rect)

class TextInput:
    def __init__(self, x, y, w, h, placeholder="Enter Host IP"):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = ""
        self.active = False
        self.placeholder = placeholder

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
            else:
                self.active = False
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_RETURN:
                return self.text
            elif event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                self.text += event.unicode
        return None

    def draw(self, screen):
        color = (200, 200, 255) if self.active else (100, 100, 100)
        pygame.draw.rect(screen, color, self.rect, 2)
        
        display_text = self.text if self.text else self.placeholder
        text_color = (255, 255, 255) if self.text else (150, 150, 150)
        
        start_x = self.rect.x + 5
        center_y = self.rect.centery
        
        font = pygame.font.Font(None, 24)
        s = font.render(display_text, True, text_color)
        r = s.get_rect(midleft=(start_x, center_y))
        screen.blit(s, r)

def show_menu(screen):
    w, h = screen.get_size()
    state = "MENU" # MENU, JOIN
    
    # Menu Buttons
    join_btn = pygame.Rect(w//2-120, h//2-40, 240, 50)
    create_btn = pygame.Rect(w//2-120, h//2+30, 240, 50)
    
    # Join Screen UI
    refresh_btn = pygame.Rect(50, 50, 100, 40)
    back_btn = pygame.Rect(50, h - 70, 100, 40)
    manual_connect_btn = pygame.Rect(w - 160, h - 70, 150, 40)
    ip_input = TextInput(w - 320, h - 70, 150, 40)
    
    found_rooms = []
    server_proc = None
    server_failed = False
    message = ""
    last_discovery = 0
    
    while True:
        events = pygame.event.get()
        for e in events:
            if e.type == pygame.QUIT:
                return None, server_proc
            
            if state == "MENU":
                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if join_btn.collidepoint(e.pos):
                        state = "JOIN"
                        message = "Searching..."
                        found_rooms = discover_rooms(timeout=0.5)
                        last_discovery = time.time()
                    
                    if create_btn.collidepoint(e.pos):
                        # ... (Same server creation logic as reference) ...
                        if server_proc is not None:
                            try:
                                server_proc.terminate()
                            except:
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
                            
                        time.sleep(0.2)
                        return ("create", "127.0.0.1"), server_proc

            elif state == "JOIN":
                # Handle Input
                manual_ip = ip_input.handle_event(e)
                if manual_ip:
                    return ("join", manual_ip), server_proc

                if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if back_btn.collidepoint(e.pos):
                        state = "MENU"
                        message = ""
                    
                    if refresh_btn.collidepoint(e.pos):
                        message = "Refreshing..."
                        # Draw immediately to show feedback
                        screen.fill((30,30,30))
                        draw_text(screen, "Refreshing...", (w//2, h//2), size=40)
                        pygame.display.flip()
                        found_rooms = discover_rooms(timeout=1.0)
                        last_discovery = time.time()
                        message = ""

                    if manual_connect_btn.collidepoint(e.pos):
                         if ip_input.text:
                             return ("join", ip_input.text), server_proc
                    
                    # Check room list clicks
                    list_start_y = 120
                    for i, room in enumerate(found_rooms):
                        rect = pygame.Rect(100, list_start_y + i * 60, w - 200, 50)
                        if rect.collidepoint(e.pos):
                            return ("join", room["host"]), server_proc

        # Drawing
        screen.fill((30,30,30))
        
        if state == "MENU":
            pygame.draw.rect(screen, (70,70,70), join_btn)
            pygame.draw.rect(screen, (70,70,70), create_btn)
            draw_text(screen, "Join Room", join_btn.center)
            draw_text(screen, "Create Room", create_btn.center)
            if message:
                msg_color = (255,100,100) if server_failed else (200,200,100)
                draw_text(screen, message, (w//2, h//2+110), size=20, color=msg_color)
                
        elif state == "JOIN":
            draw_text(screen, "Available Rooms", (w//2, 40), size=40)
            
            # Refresh Button
            pygame.draw.rect(screen, (50, 100, 50), refresh_btn)
            draw_text(screen, "Refresh", refresh_btn.center, size=24)
            
            # Back Button
            pygame.draw.rect(screen, (100, 50, 50), back_btn)
            draw_text(screen, "Back", back_btn.center, size=24)
            
            # Manual Connect UI
            ip_input.draw(screen)
            pygame.draw.rect(screen, (50, 50, 100), manual_connect_btn)
            draw_text(screen, "Connect IP", manual_connect_btn.center, size=24)

            # Room List
            list_start_y = 120
            if not found_rooms:
                draw_text(screen, "No rooms found.", (w//2, 150), color=(150,150,150))
            else:
                for i, room in enumerate(found_rooms):
                    rect = pygame.Rect(100, list_start_y + i * 60, w - 200, 50)
                    mouse_pos = pygame.mouse.get_pos()
                    bg_color = (80, 80, 80) if rect.collidepoint(mouse_pos) else (60, 60, 60)
                    
                    pygame.draw.rect(screen, bg_color, rect)
                    
                    info_text = f"Room: {room.get('room_code', '????')}   |   Host: {room['host']}"
                    draw_text(screen, info_text, (rect.centerx, rect.centery), size=28)

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
