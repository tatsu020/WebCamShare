import socket
import threading
import json
import time

# Discovery constants
DISCOVERY_PORT = 8001
DISCOVERY_MESSAGE = "WEBCAMSHARE_DISCOVER"
ANNOUNCE_MESSAGE = "WEBCAMSHARE_ANNOUNCE"


def get_local_ip():
    try:
        # Connect to an external server to determine the interface used for internet
        # We don't actually send data, just establish the route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class ServerAnnouncer:
    """Sender側: サーバーの存在をブロードキャストリクエストに応答して通知"""
    
    def __init__(self, server_port=8000):
        self.server_port = server_port
        self.running = False
        self.thread = None
        self.sock = None
    
    def start(self):
        if self.running:
            return
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', DISCOVERY_PORT))
        self.sock.settimeout(1.0)
        
        self.thread = threading.Thread(target=self._listen_and_respond, daemon=True)
        self.thread.start()
        print(f"ServerAnnouncer started on port {DISCOVERY_PORT}")
    
    def _listen_and_respond(self):
        local_ip = get_local_ip()
        while self.running:
            try:
                data, addr = self.sock.recvfrom(1024)
                if data.decode() == DISCOVERY_MESSAGE:
                    response = json.dumps({
                        "type": ANNOUNCE_MESSAGE,
                        "ip": local_ip,
                        "port": self.server_port,
                        "name": f"WebCamShare ({local_ip})"
                    })
                    self.sock.sendto(response.encode(), addr)
                    print(f"Responded to discovery request from {addr}")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"Announcer error: {e}")
                continue
    
    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        print("ServerAnnouncer stopped")


class ServerDiscovery:
    """Receiver側: LANでサーバーを検出"""
    
    def __init__(self, timeout=3.0):
        self.timeout = timeout
    
    def discover(self):
        """サーバーを検索し、見つかったサーバーのリストを返す"""
        servers = []
        seen_ips = set()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        
        try:
            # ブロードキャストで検索メッセージを送信
            sock.sendto(DISCOVERY_MESSAGE.encode(), ('<broadcast>', DISCOVERY_PORT))
            
            start_time = time.time()
            while time.time() - start_time < self.timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    response = json.loads(data.decode())
                    if response.get("type") == ANNOUNCE_MESSAGE:
                        ip = response["ip"]
                        if ip not in seen_ips:
                            seen_ips.add(ip)
                            servers.append({
                                "ip": ip,
                                "port": response["port"],
                                "name": response["name"]
                            })
                except socket.timeout:
                    # タイムアウトでも継続して待機
                    continue
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue
        finally:
            sock.close()
        
        return servers
