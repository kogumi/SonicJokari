"""Lecture des Wiimotes — deux pilotes au choix :

  evdev  : Linux / Raspberry Pi, via le pilote natif du noyau (hid-wiimote). Le plus fiable.
  hidapi : Mac / Windows (et Linux), en parlant directement le protocole Wiimote.
           Sur Mac récent, passer par une Mayflash DolphinBar (mode 4) : le Bluetooth
           natif de macOS ne connecte plus les Wiimotes.

Détections communes (classe Detector) :
  - coup   : geste ample (pic d'accélération > seuil_coup), force 0..1
  - choc   : impact sec et bref (forte variation d'un échantillon à l'autre) -> trinquer
  - motion : intensité de mouvement lissée, pour le son « sabre »
"""
import math
import os
import re
import select
import sys
import threading
import time

try:
    import evdev
    from evdev import ecodes, ff
except ImportError:
    evdev = None

try:
    import hid  # paquet pip « hidapi »
except ImportError:
    hid = None

NINTENDO = 0x057E
WIIMOTE_PIDS = (0x0306, 0x0330)   # RVL-CNT-01 et RVL-CNT-01-TR (Wiimote Plus)


# ======================================================================
#  Détection des gestes (indépendante du pilote)
#  Entrée : accélération x, y, z avec ~100 unités = 1 g, centrée sur 0.
# ======================================================================
class Detector:
    def __init__(self, cfg, emit):
        self.cfg, self.emit = cfg, emit
        self.motion = 0.0
        self._g = 100.0
        self._prev = None
        self._in_swing = False
        self._peak = self._onset = self._refract = self._choc_refract = 0.0
        self.last_peak = 0.0

    def feed(self, x, y, z, ts):
        c = self.cfg
        mag = math.sqrt(x * x + y * y + z * z)
        dyn = abs(mag - self._g) / self._g
        if dyn < 0.08:                                   # au repos : recalibre la gravité
            self._g += (mag - self._g) * 0.02
        self.motion = dyn if dyn > self.motion else self.motion * 0.93

        if self._prev is not None:                       # choc (trinquer)
            px, py, pz = self._prev
            jerk = math.sqrt((x - px) ** 2 + (y - py) ** 2 + (z - pz) ** 2) / self._g
            if jerk > c["seuil_choc"] and ts > self._choc_refract:
                self._choc_refract = ts + 0.25
                self.emit("choc", ts)
        self._prev = (x, y, z)

        if not self._in_swing:                           # coup
            if dyn > c["seuil_coup"] and ts > self._refract:
                self._in_swing, self._peak, self._onset = True, dyn, ts
        elif dyn > self._peak:
            self._peak = dyn
        elif dyn < self._peak * 0.85 or ts - self._onset > 0.08:
            self._in_swing = False
            self._refract = ts + c["refractaire"]
            span = max(c["force_max"] - c["seuil_coup"], 0.1)
            self.last_peak = self._peak                    # pic du geste, en g (affiché pour régler)
            self.emit("coup", min(max((self._peak - c["seuil_coup"]) / span, 0.0), 1.0))


class BaseRemote:
    """Interface commune : slot, alive, active, motion, rumble(ms), set_leds(slot), close()."""

    def __init__(self, uid, cfg, on_event):
        self.uid = uid
        self.slot = None
        self.alive = True
        self.active = True
        self.enabled = True     # désactivable depuis la page de réglages
        self.on_event = on_event
        self.det = Detector(cfg, lambda k, v: self.on_event(self, k, v))

    @property
    def motion(self):
        return self.det.motion

    def button(self, name):
        self.on_event(self, "bouton", name)


# ======================================================================
#  Pilote evdev (Linux / Pi)
# ======================================================================
CORE_NAME = "Nintendo Wii Remote"
ACC_NAME = "Nintendo Wii Remote Accelerometer"
HID_RE = re.compile(r"^[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}$")
EV_BUTTONS = {}
if evdev:
    EV_BUTTONS = {ecodes.BTN_MODE: "home", ecodes.KEY_NEXT: "plus", ecodes.KEY_PREVIOUS: "moins",
                  ecodes.BTN_A: "a", ecodes.BTN_B: "b", ecodes.BTN_1: "1", ecodes.BTN_2: "2"}


def _hid_dir(dev_path):
    p = os.path.realpath(f"/sys/class/input/{os.path.basename(dev_path)}/device")
    while p and p != "/":
        if HID_RE.match(os.path.basename(p)):
            return p
        p = os.path.dirname(p)
    return None


class EvdevRemote(BaseRemote):
    def __init__(self, hid_dir, core, acc, cfg, on_event):
        super().__init__(hid_dir, cfg, on_event)
        self.core, self.acc = core, acc
        self._xyz = [0, 0, 100]
        self._ff_id = -1
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        devs = {self.core.fd: self.core, self.acc.fd: self.acc}
        try:
            while self.alive:
                r, _, _ = select.select(list(devs), [], [], 1.0)
                for fd in r:
                    for ev in devs[fd].read():
                        if devs[fd] is self.acc:
                            if ev.type == ecodes.EV_ABS:
                                i = {ecodes.ABS_RX: 0, ecodes.ABS_RY: 1, ecodes.ABS_RZ: 2}.get(ev.code)
                                if i is not None:
                                    self._xyz[i] = ev.value
                            elif ev.type == ecodes.EV_SYN:
                                self.det.feed(*self._xyz, ev.timestamp())
                        elif ev.type == ecodes.EV_KEY and ev.value == 1 and ev.code in EV_BUTTONS:
                            self.button(EV_BUTTONS[ev.code])
        except (OSError, IOError):
            pass
        self.alive = False

    def rumble(self, ms):
        if ms <= 0 or not self.alive:
            return
        try:
            with self._lock:
                eff = ff.Effect(ecodes.FF_RUMBLE, self._ff_id, 0, ff.Trigger(0, 0),
                                ff.Replay(int(ms), 0),
                                ff.EffectType(ff_rumble_effect=ff.Rumble(0xFFFF, 0xFFFF)))
                self._ff_id = self.core.upload_effect(eff)
                self.core.write(ecodes.EV_FF, self._ff_id, 1)
        except OSError:
            pass

    def set_leds(self, slot):
        base = os.path.join(self.uid, "leds")
        try:
            for name in os.listdir(base):
                m = re.search(r":p(\d)$", name)
                if m:
                    with open(os.path.join(base, name, "brightness"), "w") as f:
                        f.write("1" if int(m.group(1)) == slot % 4 else "0")
        except OSError:
            pass

    def close(self):
        self.alive = False
        for d in (self.core, self.acc):
            try:
                d.close()
            except Exception:
                pass


def scan_evdev(known, cfg, on_event):
    found, groups = [], {}
    for path in evdev.list_devices():
        try:
            d = evdev.InputDevice(path)
        except OSError:
            continue
        hdir = _hid_dir(path)
        if d.name not in (CORE_NAME, ACC_NAME) or not hdir or hdir in known:
            d.close()
            continue
        groups.setdefault(hdir, {})[d.name] = d
    for hdir, devs in groups.items():
        if CORE_NAME in devs and ACC_NAME in devs:
            found.append(EvdevRemote(hdir, devs[CORE_NAME], devs[ACC_NAME], cfg, on_event))
        else:
            for d in devs.values():
                d.close()
    return found


# ======================================================================
#  Pilote hidapi (Mac / Windows / DolphinBar) — protocole Wiimote brut
# ======================================================================
HID_BUTTONS = [(1, 0x10, "plus"), (2, 0x01, "2"), (2, 0x02, "1"), (2, 0x04, "b"),
               (2, 0x08, "a"), (2, 0x10, "moins"), (2, 0x80, "home")]


class _WinWriter:
    """Repli Windows : HidD_SetOutputReport (pile Bluetooth Microsoft avec Wiimotes d'origine)."""

    def __init__(self, path):
        import ctypes
        from ctypes import wintypes
        self.ct = ctypes
        k32, self.hidd = ctypes.windll.kernel32, ctypes.windll.hid
        k32.CreateFileW.restype = wintypes.HANDLE
        self.h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)
        if self.h in (None, wintypes.HANDLE(-1).value):
            raise OSError("CreateFile a échoué")

    def write(self, data):
        buf = (self.ct.c_ubyte * 22)(*(list(data) + [0] * (22 - len(data))))
        return 22 if self.hidd.HidD_SetOutputReport(self.ct.c_void_p(self.h), buf, 22) else -1


class HidRemote(BaseRemote):
    def __init__(self, info, cfg, on_event):
        path = info["path"]
        super().__init__(path, cfg, on_event)
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(False)
        self.active = False            # DolphinBar : l'interface existe même sans Wiimote
        self._last = 0.0
        self._rumble_on = False
        self._leds = 0
        self._cal = None               # (zéro, 1g) par axe
        self._buttons = (0, 0)
        self._got_accel = 0.0
        self._writer = None
        self._mode_sent = 0.0
        self._win_path = path.decode() if isinstance(path, bytes) else path
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    # ----- écriture -----
    def _write(self, data):
        with self._lock:
            try:
                if self._writer:
                    return self._writer.write(data)
                return self.dev.write(list(data))
            except (OSError, ValueError):
                return -1

    def _rb(self):
        return 0x01 if self._rumble_on else 0x00

    def _send_mode(self):
        self._mode_sent = time.monotonic()
        self._write([0x12, 0x04 | self._rb(), 0x31])     # boutons + accéléro, en continu

    def _probe(self):
        self._write([0x15, self._rb()])                   # demande de statut

    def _read_calibration(self):
        self._write([0x17, 0x00 | self._rb(), 0x00, 0x00, 0x16, 0x00, 0x0A])

    # ----- lecture -----
    def _run(self):
        last_probe = 0.0
        while self.alive:
            try:
                data = self.dev.read(32, 200)
            except (OSError, ValueError):
                break
            now = time.monotonic()
            if data:
                if not self.active:
                    self.active = True
                    self._send_mode()
                    self._read_calibration()
                self._last = now
                self._handle(data, now)
            # sans réponse en mode continu : essai du repli Windows, puis sondage
            if self.active and now - self._got_accel > 1.0 and now - self._mode_sent > 1.0:
                if sys.platform == "win32" and self._writer is None and self._mode_sent:
                    try:
                        self._writer = _WinWriter(self._win_path)
                        print("[wiimote] Windows : écriture via HidD_SetOutputReport")
                    except Exception:
                        self._writer = False
                self._send_mode()
            if self.active and now - self._last > 3.0:
                self.active = False                        # Wiimote éteinte / hors de portée
            if not self.active and now - last_probe > 1.0:
                last_probe = now
                self._probe()
        self.alive = False

    def _handle(self, d, now):
        rid = d[0]
        if len(d) >= 3:
            b = (d[1], d[2])
            if b != self._buttons:
                for idx, mask, name in HID_BUTTONS:
                    if b[idx - 1] & mask and not self._buttons[idx - 1] & mask:
                        self.button(name)
                self._buttons = b
        if rid == 0x20:                                    # statut : il faut redonner le mode
            self._send_mode()
        elif rid == 0x21 and len(d) >= 14 and (d[3] & 0x0F) == 0:
            c = d[6:14]
            zero = [(c[0] << 2) | ((c[3] >> 4) & 3), (c[1] << 2) | ((c[3] >> 2) & 3), (c[2] << 2) | (c[3] & 3)]
            one = [(c[4] << 2) | ((c[7] >> 4) & 3), (c[5] << 2) | ((c[7] >> 2) & 3), (c[6] << 2) | (c[7] & 3)]
            if all(o - z > 20 for o, z in zip(one, zero)):
                self._cal = (zero, one)
        elif rid == 0x31 and len(d) >= 6:
            self._got_accel = now
            raw = [(d[3] << 2) | ((d[1] >> 5) & 3),
                   (d[4] << 2) | (((d[2] >> 4) & 1) << 1),
                   (d[5] << 2) | (((d[2] >> 5) & 1) << 1)]
            if self._cal:
                zero, one = self._cal
                xyz = [(r - z) * 100.0 / (o - z) for r, z, o in zip(raw, zero, one)]
            else:
                xyz = [float(r - 512) for r in raw]
            self.det.feed(*xyz, now)

    # ----- sorties -----
    def rumble(self, ms):
        if ms <= 0 or not self.active:
            return
        self._rumble_on = True
        self._write([0x10, 0x01])
        time.sleep(ms / 1000)
        self._rumble_on = False
        self._write([0x10, 0x00])

    def set_leds(self, slot):
        self._leds = 1 << (slot % 4)
        self._write([0x11, (self._leds << 4) | self._rb()])

    def close(self):
        self.alive = False
        try:
            self.dev.close()
        except Exception:
            pass


def scan_hidapi(known, cfg, on_event):
    found = []
    for info in hid.enumerate(NINTENDO, 0):
        if info.get("product_id") not in WIIMOTE_PIDS or info["path"] in known:
            continue
        try:
            found.append(HidRemote(info, cfg, on_event))
        except (OSError, IOError) as e:
            print("[wiimote] ouverture impossible :", e)
    return found


# ======================================================================
#  Gestionnaire : numéros de joueurs, connexions / déconnexions
# ======================================================================
def choose_backend(pref):
    if pref == "evdev" or (pref == "auto" and sys.platform.startswith("linux") and evdev):
        return "evdev" if evdev else None
    if pref in ("hidapi", "auto"):
        return "hidapi" if hid else None
    return None


class WiimoteManager:
    def __init__(self, cfg, on_event):
        self.cfg = cfg
        self.on_event = on_event
        self.remotes = {}       # slot -> remote actif
        self._all = {}          # uid -> remote (actif ou non)
        self._new = []          # manettes ajoutées depuis un autre fil (téléphones)
        self.backend = choose_backend(cfg["manette"].get("pilote", "auto"))
        self.available = self.backend is not None
        if self.available:
            print(f"[wiimote] pilote : {self.backend}")
        threading.Thread(target=self._loop, daemon=True).start()

    def add(self, remote):
        """Ajoute une manette venue d'ailleurs (téléphone) ; prise en compte au prochain tour."""
        self._new.append(remote)

    def _loop(self):
        while True:
            try:
                self._scan()
            except Exception as e:
                print("[wiimote] erreur de scan :", e)
            time.sleep(0.25)

    def _scan(self):
        while self._new:
            r = self._new.pop(0)
            self._all[r.uid] = r
        for uid, r in list(self._all.items()):
            if not r.alive:
                r.close()
                del self._all[uid]
        for slot, r in list(self.remotes.items()):
            if not (r.alive and r.active and r.enabled):
                print(f"[wiimote] joueur {slot + 1} déconnecté")
                r.slot = None
                del self.remotes[slot]
        now = time.monotonic()
        if self.backend and now - getattr(self, "_last_hw", 0.0) >= 1.0:   # matériel : 1 fois/s
            self._last_hw = now
            scan = scan_evdev if self.backend == "evdev" else scan_hidapi
            for r in scan(set(self._all), self.cfg["manette"], self.on_event):
                self._all[r.uid] = r
        for r in self._all.values():
            if r.alive and r.active and r.enabled and r.slot is None:
                slot = 0
                while slot in self.remotes:
                    slot += 1
                r.slot = slot
                self.remotes[slot] = r
                r.set_leds(slot)
                self.rumble(slot, 300)
                print(f"[wiimote] joueur {slot + 1} connecté")

    def listing(self):
        """Toutes les raquettes connues (téléphones et Wiimotes), pour la page de réglages."""
        out = []
        for uid, r in list(self._all.items()):
            phone = uid.startswith("tel:")
            out.append({"id": uid, "type": "téléphone" if phone else "Wiimote",
                        "nom": getattr(r, "name", "") or "", "joueur": None if r.slot is None else r.slot + 1,
                        "actif": r.enabled, "en_ligne": bool(r.alive and r.active)})
        return sorted(out, key=lambda x: (x["joueur"] is None, x["joueur"] or 0, x["id"]))

    def set_enabled(self, uid, on):
        r = self._all.get(uid)
        if r:
            r.enabled = bool(on)

    def rumble(self, slot, ms):
        r = self.remotes.get(slot)
        if r:
            threading.Thread(target=r.rumble, args=(ms,), daemon=True).start()

    def motion(self, slot):
        r = self.remotes.get(slot)
        return r.motion if r else None
