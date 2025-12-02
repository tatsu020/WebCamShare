import socket

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
