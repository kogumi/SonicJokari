"""OSC minimal (UDP) — sans dépendance externe."""
import socket
import struct


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (4 - len(b) % 4)


def encode(address: str, *args) -> bytes:
    tags, data = ",", b""
    for a in args:
        if isinstance(a, bool):
            a = int(a)
        if isinstance(a, int):
            tags += "i"
            data += struct.pack(">i", a)
        elif isinstance(a, float):
            tags += "f"
            data += struct.pack(">f", a)
        elif isinstance(a, str):
            tags += "s"
            data += _pad(a.encode("utf-8"))
        else:
            raise TypeError(f"type OSC non géré : {type(a)}")
    return _pad(address.encode()) + _pad(tags.encode()) + data


def _read_str(p: bytes, i: int):
    j = p.index(b"\0", i)
    s = p[i:j].decode("utf-8", "replace")
    return s, (j + 4) & ~3


def decode(packet: bytes):
    addr, i = _read_str(packet, 0)
    if i >= len(packet):
        return addr, []
    tags, i = _read_str(packet, i)
    args = []
    for t in tags[1:]:
        if t == "i":
            args.append(struct.unpack(">i", packet[i:i + 4])[0]); i += 4
        elif t == "f":
            args.append(struct.unpack(">f", packet[i:i + 4])[0]); i += 4
        elif t == "s":
            s, i = _read_str(packet, i); args.append(s)
        else:
            break
    return addr, args


class OscClient:
    def __init__(self, host="127.0.0.1", port=57120):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, address, *args):
        try:
            self.sock.sendto(encode(address, *args), self.addr)
        except OSError:
            pass
