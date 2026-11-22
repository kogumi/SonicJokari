"""Téléphone comme raquette.

La page /raquette (servie en HTTPS, obligatoire pour lire les capteurs de mouvement)
envoie l'accéléromètre du téléphone par petits paquets. On le passe dans le même
Detector que les Wiimotes : coup, choc et intensité de mouvement pour le sabre.
Le téléphone reçoit en retour son numéro de joueur et les ordres de vibration.
"""
import os
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time

from wiimote import BaseRemote

G = 9.81
STALE = 3.0      # s sans données -> le joueur est libéré
FORGET = 60.0    # s sans données -> le téléphone est oublié


class PhoneRemote(BaseRemote):
    def __init__(self, uid, cfg, manette_cfg, on_event):
        self.last = time.monotonic()
        self._vibre = 0
        self._lock = threading.Lock()
        self._mcfg = manette_cfg
        self._offset = None      # horloge du téléphone -> horloge du jeu
        self._choc = False
        self.name = ""        # prénom saisi sur le téléphone
        super().__init__(uid, cfg, on_event)
        emit = self.det.emit

        def emit_and_mark(kind, value):  # signale au téléphone qu'il a senti un choc (trinquer)
            if kind == "choc":
                self._choc = True
            emit(kind, value)
        self.det.emit = emit_and_mark

    # actif / vivant d'après l'arrivée des données (le gestionnaire ne fait que lire)
    @property
    def active(self):
        return time.monotonic() - self.last < STALE

    @active.setter
    def active(self, v):
        pass

    @property
    def alive(self):
        return time.monotonic() - self.last < FORGET

    @alive.setter
    def alive(self, v):
        pass

    @property
    def motion(self):
        # ramené à l'échelle des Wiimotes pour le son du sabre
        return self.det.motion * self._mcfg["force_max"] / max(self.det.cfg.get("sensibilite_sabre", 4.0), 0.1)

    def feed(self, samples):
        """samples : [[t_ms, x, y, z], ...] en m/s², gravité comprise, horloge du téléphone."""
        now = time.monotonic()
        self.last = now
        if not samples:
            return
        t_end = samples[-1][0] / 1000
        # horloge du téléphone recalée sur celle du jeu : on garde le décalage le plus petit vu
        # (le paquet arrivé le plus vite), qui ne dépend plus de la gigue du Wi-Fi. Il peut
        # remonter très lentement pour suivre la dérive des horloges.
        est = now - t_end
        if self._offset is None or est < self._offset or abs(est - self._offset) > 2.0:
            self._offset = est
        else:
            self._offset += min(est - self._offset, 0.0005)
        with self._lock:
            for t, x, y, z in samples:
                self.det.feed(x * 100 / G, y * 100 / G, z * 100 / G, t / 1000 + self._offset)

    def take_choc(self):
        c, self._choc = self._choc, False
        return c

    def take_vibration(self):
        ms, self._vibre = self._vibre, 0
        return ms

    def rumble(self, ms):
        self._vibre = max(self._vibre, int(ms))

    def set_leds(self, slot):
        pass

    def close(self):
        pass


class PhoneHub:
    """Associe un identifiant de téléphone à sa PhoneRemote et l'annonce au gestionnaire."""

    def __init__(self, cfg, manager, on_event):
        self.cfg, self.mgr, self.on_event = cfg, manager, on_event
        self.phones = {}
        self._lock = threading.Lock()

    def get(self, pid):
        with self._lock:
            r = self.phones.get(pid)
            if r is None or not r.alive:
                r = PhoneRemote("tel:" + pid, self.cfg["telephone"], self.cfg["manette"], self.on_event)
                self.phones[pid] = r
                self.mgr.add(r)
                print("[téléphone] nouvelle raquette")
            return r


def ensure_cert(folder, ip, name=""):
    """Certificat auto-signé pour le HTTPS, créé avec openssl (et refait si l'IP change).
    Il respecte les exigences d'Apple, sinon l'iPhone refuse sans proposer de passer outre :
    825 jours maximum, SAN avec l'IP, usage serverAuth."""
    cert, key = os.path.join(folder, "cert.pem"), os.path.join(folder, "key.pem")
    tag = os.path.join(folder, "ip.txt")
    try:
        with open(tag) as f:
            same_ip = f.read().strip() == f"{ip} {name}"
    except OSError:
        same_ip = False
    if same_ip and os.path.isfile(cert) and os.path.isfile(key):
        return cert, key
    exe = shutil.which("openssl")
    if not exe:
        return None
    os.makedirs(folder, exist_ok=True)
    try:
        subprocess.run([exe, "req", "-x509", "-newkey", "rsa:2048", "-sha256", "-nodes",
                        "-keyout", key, "-out", cert, "-days", "820", "-subj", "/CN=jokari-sonore",
                        "-addext", f"subjectAltName=IP:{ip},IP:127.0.0.1,DNS:localhost" + (f",DNS:{name}" if name else ""),
                        "-addext", "extendedKeyUsage=serverAuth",
                        "-addext", "basicConstraints=critical,CA:FALSE",
                        "-addext", "keyUsage=critical,digitalSignature,keyEncipherment"],
                       check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(tag, "w") as f:
            f.write(f"{ip} {name}")
    except Exception:
        return None
    print(f"[téléphone] nouveau certificat HTTPS pour {ip} {name}")
    return cert, key


def wrap_https(server, cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    # poignée de main faite dans le fil de chaque requête, pas dans la boucle d'accueil
    server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    # Safari ouvre des connexions annexes qui refusent le certificat auto-signé : sans gravité,
    # on ne les affiche pas (les autres erreurs restent visibles).
    default = server.handle_error

    def quiet(request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (ssl.SSLError, ConnectionError, TimeoutError)):
            return
        default(request, client_address)
    server.handle_error = quiet


def local_ip():
    """Adresse IP sur le réseau local (aucun paquet n'est envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def local_name():
    """Nom fixe de la machine sur le réseau local (mDNS, « xxx.local ») : il ne change pas
    quand l'adresse IP change, d'où son emploi dans le QR code. Mac : nom Bonjour ;
    Linux / Pi : nom d'hôte (avahi) ; Windows : nom d'hôte."""
    if sys.platform == "darwin":
        try:
            n = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=3).stdout.strip()
            if n:
                return n + ".local"
        except Exception:
            pass
    n = socket.gethostname().split(".")[0]
    return n + ".local" if n else ""
