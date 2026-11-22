"""QR code minimal, sans dépendance (mode octet, correction M, versions 1 à 10 : jusqu'à 213 octets).

    qr.svg("https://exemple.local:8443/raquette")   -> texte SVG
    qr.png("WIFI:T:WPA;S:reseau;P:motdepasse;;")      -> octets PNG

D'après l'algorithme de référence (ISO/IEC 18004), dans l'esprit de la bibliothèque de Nayuki.
"""
import struct
import zlib

# (codes correcteurs par bloc, [(nombre de blocs, octets de données par bloc), ...]) — niveau M
_BLOCKS = {1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]),
           5: (24, [(2, 43)]), 6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]),
           9: (22, [(3, 36), (2, 37)]), 10: (26, [(4, 43), (1, 44)])}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34],
          7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}
_ECL_M = 0   # bits de format du niveau M


def _mul(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree):
    res = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            res[j] = _mul(res[j], root)
            if j + 1 < degree:
                res[j] ^= res[j + 1]
        root = _mul(root, 2)
    return res


def _rs_remainder(data, div):
    res = [0] * len(div)
    for b in data:
        factor = b ^ res.pop(0)
        res.append(0)
        for i, c in enumerate(div):
            res[i] ^= _mul(c, factor)
    return res


def _codewords(text):
    data = text.encode("utf-8")
    for ver in range(1, 11):
        ecc, groups = _BLOCKS[ver]
        cap = sum(n * k for n, k in groups)
        cbits = 8 if ver < 10 else 16
        eci = 12 if any(b > 127 for b in data) else 0   # accents : on déclare l'UTF-8 (ECI 26)
        if eci + 4 + cbits + 8 * len(data) <= cap * 8:
            break
    else:
        raise ValueError("texte trop long pour le QR code (213 octets max)")
    bits = [0, 1, 1, 1] + [(26 >> i) & 1 for i in reversed(range(8))] if eci else []
    bits += [0, 1, 0, 0] + [(len(data) >> i) & 1 for i in reversed(range(cbits))]
    for b in data:
        bits += [(b >> i) & 1 for i in reversed(range(8))]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)
    out = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(out) < cap:
        out.append(pad)
        pad ^= 0xEC ^ 0x11
    # découpe en blocs, codes correcteurs, entrelacement
    div = _rs_divisor(ecc)
    blocks, k = [], 0
    for n, size in groups:
        for _ in range(n):
            blocks.append((out[k:k + size], _rs_remainder(out[k:k + size], div)))
            k += size
    res = []
    for i in range(max(len(d) for d, _ in blocks)):
        res += [d[i] for d, _ in blocks if i < len(d)]
    for i in range(ecc):
        res += [e[i] for _, e in blocks]
    return ver, res


def matrix(text):
    """Renvoie la matrice du QR code (liste de lignes de booléens, True = noir)."""
    ver, cw = _codewords(text)
    n = ver * 4 + 17
    mod = [[False] * n for _ in range(n)]
    fn = [[False] * n for _ in range(n)]

    def setf(x, y, v):
        mod[y][x] = bool(v)
        fn[y][x] = True

    for i in range(n):                                   # motifs de synchronisation
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):      # repères des coins (+ séparateurs)
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    setf(x, y, max(abs(dx), abs(dy)) not in (2, 4))
    al = _ALIGN[ver]                                     # motifs d'alignement
    for i, ax in enumerate(al):
        for j, ay in enumerate(al):
            if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                continue
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    setf(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)

    def format_bits(mask):
        data = _ECL_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        g = lambda i: (bits >> i) & 1
        for i in range(6):
            setf(8, i, g(i))
        setf(8, 7, g(6))
        setf(8, 8, g(7))
        setf(7, 8, g(8))
        for i in range(9, 15):
            setf(14 - i, 8, g(i))
        for i in range(8):
            setf(n - 1 - i, 8, g(i))
        for i in range(8, 15):
            setf(8, n - 15 + i, g(i))
        setf(8, n - 8, 1)                                # module toujours noir

    format_bits(0)                                       # réserve les zones de format
    if ver >= 7:                                         # informations de version
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            b = (bits >> i) & 1
            a, c = n - 11 + i % 3, i // 3
            setf(a, c, b)
            setf(c, a, b)

    i = 0                                                # placement en zigzag
    for right in range(n - 1, 0, -2):
        if right <= 6:
            right -= 1
        for vert in range(n):
            for j in range(2):
                x = right - j
                up = ((right + 1) & 2) == 0
                y = n - 1 - vert if up else vert
                if not fn[y][x] and i < len(cw) * 8:
                    mod[y][x] = bool((cw[i >> 3] >> (7 - (i & 7))) & 1)
                    i += 1

    masks = [lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0]

    def apply(m):
        for y in range(n):
            for x in range(n):
                if not fn[y][x] and masks[m](x, y):
                    mod[y][x] = not mod[y][x]

    def penalty():                                       # règles 1, 2 et 4 de la norme
        p = 0
        for grid in (mod, [list(c) for c in zip(*mod)]):
            for row in grid:
                run = 1
                for a, b in zip(row, row[1:]):
                    if a == b:
                        run += 1
                    else:
                        p += run - 2 if run >= 5 else 0
                        run = 1
                p += run - 2 if run >= 5 else 0
        for y in range(n - 1):
            for x in range(n - 1):
                if mod[y][x] == mod[y][x + 1] == mod[y + 1][x] == mod[y + 1][x + 1]:
                    p += 3
        dark = sum(map(sum, mod))
        p += abs(dark * 20 - n * n * 10) // (n * n) * 10
        return p

    best = None
    for m in range(8):
        apply(m)
        format_bits(m)
        sc = penalty()
        if best is None or sc < best[0]:
            best = (sc, m)
        apply(m)                                         # annule (le masque est son propre inverse)
    apply(best[1])
    format_bits(best[1])
    return mod


def svg(text, scale=8, border=4, color="#000"):
    m = matrix(text)
    n = len(m) + border * 2
    path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(m) for x, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" height="{n * scale}" '
            f'shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/>'
            f'<path d="{path}" fill="{color}"/></svg>')


def png(text, scale=10, border=4):
    m = matrix(text)
    n = (len(m) + border * 2) * scale
    rows = []
    for y in range(n):
        my = y // scale - border
        line = bytearray([0])
        for x in range(n):
            mx = x // scale - border
            dark = 0 <= my < len(m) and 0 <= mx < len(m) and m[my][mx]
            line.append(0 if dark else 255)
        rows.append(bytes(line))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def wifi_text(ssid, password, security="WPA"):
    esc = lambda s: "".join("\\" + c if c in '\\;,:"' else c for c in s)
    if not password:
        return f"WIFI:T:nopass;S:{esc(ssid)};;"
    return f"WIFI:T:{security};S:{esc(ssid)};P:{esc(password)};;"
