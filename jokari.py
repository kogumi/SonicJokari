#!/usr/bin/env python3
"""Sonic Jokari — jeu de raquette sans image, guidé uniquement par le son.

Python : manettes Wii ou téléphones, logique de jeu, vibreurs, page web de réglages.
SuperCollider (sc/jokari.scd) : tout le son, piloté en OSC.
Téléphone comme raquette : https://IP-DE-LA-MACHINE:8443/raquette

Usage :
  python3 jokari.py            # normal (manettes + SuperCollider)
  python3 jokari.py --sim      # ajoute 2 joueurs virtuels (boutons sur la page web)
  python3 jokari.py --no-sc    # ne lance pas SuperCollider (s'il tourne déjà ailleurs)
"""
import argparse
import copy
import glob
import html
import json
import math
import os
import queue
import random
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import audio
import osc
import qr
from phone import PhoneHub, ensure_cert, local_ip, local_name, wrap_https
from wiimote import WiimoteManager

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
SAMPLES_DIR = os.path.join(HERE, "samples")
PRESETS_DIR = os.path.join(HERE, "presets")
QR_DIR = os.path.join(HERE, "qr")
KITS_DIR = os.path.join(HERE, "kits")


def list_kits():
    """Kits de samples (kits/*.json) : [[nom de fichier, titre], ...]."""
    out = []
    for f in sorted(glob.glob(os.path.join(KITS_DIR, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                out.append([os.path.basename(f)[:-5], json.load(fh).get("nom", os.path.basename(f))])
        except (OSError, ValueError):
            pass
    return out


def load_kit(name):
    if not name:
        return None
    try:
        with open(os.path.join(KITS_DIR, os.path.basename(name) + ".json"), encoding="utf-8") as f:
            kit = json.load(f)
    except (OSError, ValueError):
        return None
    kit["dossier"] = os.path.join(HERE, kit.get("dossier", ""))
    return kit
SOUND_KINDS = ["impact", "mur", "elastique", "faute", "point", "service", "victoire", "trinque", "parfait", "riser"]
SAMPLE_EXT = (".wav", ".aif", ".aiff", ".flac")


def _snd(hauteur_force=0.0, reverb=0.1, volume=0.0, volume_force=0.0):
    return {"sample": "", "hauteur": 0.0, "hauteur_random": 1.0, "hauteur_force": hauteur_force,
            "volume": volume, "volume_force": volume_force, "volume_random": 2.0, "filtre_random": 0.1, "reverb": reverb}


DEFAULTS = {
    "jeu": {"mode": "jokari", "points_victoire": 7, "joueurs_virtuels": 0, "ecart_stereo": 0.8,
            "annonce_score": True, "rappel_service": 8.0, "trinquer_pour_lancer": True,
            "fenetre_trinque": 0.08, "adversaires_virtuels": 0, "niveau_adversaire": 0.6},
    "manette": {"pilote": "auto", "seuil_coup": 1.3, "force_max": 3.5, "refractaire": 0.35, "seuil_choc": 1.8,
                "vibreur_coup": 90, "vibreur_faute": 450, "vibreur_approche": False},
    "telephone": {"seuil_coup": 1.3, "force_max": 40.0, "sensibilite_sabre": 4.0, "refractaire": 0.35, "seuil_choc": 1.0,
                  "fenetre_trinque": 0.25,
                  "sabre_sur_telephone": True, "volume_sabre": 0.7, "transposition": 2,
                  "son_impact": True, "volume_impact": 0.8},
    "physique": {"vitesse_max": 12.0, "vitesse_min": 2.5, "courbe_force": 1.4, "transfert": 0.25, "fenetre": 4.0,
                 "moment_parfait": -0.03, "tolerance_parfait_s": 0.12, "bonus_parfait": 2.5, "retard_max": 0.25,
                 "tension_debut": 6.0,
                 "longueur_elastique": 5.0, "raideur": 1.5, "etirement_max": 10.0, "rebond_elastique": 0.25,
                 "ralenti": 0.6, "seuil_lent": 0.35,
                 "mur_distance": 10.0, "frottement": 0.08, "frein": 0.25, "restitution": 0.85,
                 "vitesse_retour_min": 2.5},
    "balle": {"frequence": 90.0, "desaccord": 0.4, "fm": 1.2, "grain": 0.3, "vibrato": 5.0,
              "volume": 0.6, "filtre_pres": 6000.0, "filtre_loin": 400.0, "reverb_pres": 0.1,
              "reverb_loin": 0.7, "attenuation": 0.25, "doppler": 1.0, "vitesse_son": 25.0,
              "tension": 1.0, "depart_grave": -7.0, "montee_combo": 19.0, "riser": True,
              "hauteur_force": 12.0, "variation_force": 1.0, "calme_doux": 0.8,
              "indicatif": 0.6, "indicatif_avance": 0.5, "souffle_retour": 0.5},
    "arpegiateur": {"actif": True, "seuil": 0.35, "volume": 0.5, "tempo": 5.0, "octave": 1, "motif": 0,
                    "reverb": 0.3},
    "sabre": {"frequence": 70.0, "ecart_joueurs": 5.0, "volume": 0.35, "brillance": 1.0,
              "grain": 0.5, "repos": 0.2, "reverb": 0.15},
    "sons": {
        "impact": _snd(hauteur_force=5.0, volume_force=16.0),
        "mur": _snd(reverb=0.5),
        "elastique": _snd(reverb=0.4),
        "faute": _snd(),
        "point": _snd(),
        "service": _snd(volume=-6.0),
        "victoire": _snd(),
        "trinque": _snd(reverb=0.3),
        "riser": _snd(hauteur_force=7.0, reverb=0.35, volume=-3.0),
        "parfait": _snd(reverb=0.3),
    },
    "combo": {"actif": True, "echanges_max": 12, "bonus_parfait": 2, "acceleration": 0.5,
              "erratique": 1.0, "couches": 1.0, "annonce_tous": 5, "raideur_combo": 1.0},
    "reverb": {"taille": 0.85, "amorti": 0.4},
    "general": {"volume": 0.9, "voix": "fr", "sortie_audio": "", "style": ""},
    # enveloppes de vol de la balle : points (phase 0 = frappe, 0,5 = élastique / mur, 1 = arrivée, valeur)
    "enveloppes": {"volume": [[0, 1], [1, 1]], "filtre": [[0, 0], [1, 0]],
                   "hauteur": [[0, 0], [1, 0]], "reverb": [[0, 0], [1, 0]]},
    "dubstep": {"wobble": 0.0},      # 0 : le wobble masquait la sensation de distance et de vitesse
    "musical": {"actif": False, "bpm": 140.0, "volume": 0.6},
    "reseau": {"wifi_nom": "SonicJokari", "wifi_mdp": "sonicjokari", "wifi_securite": "WPA", "adresse": ""},   # borne ESP32
}

# Description des réglages pour la page web : (clé, libellé, min, max, pas)
SCHEMA = [
    ("Jeu", "jeu", [
        ("mode", "Mode", "choix", [["jokari", "Jokari (élastique)"], ["pelote", "Pelote (mur au fond)"]]),
        ("points_victoire", "Points pour gagner", 1, 21, 1),
        ("adversaires_virtuels", "Adversaires virtuels (jouent seuls)", 0, 3, 1),
        ("niveau_adversaire", "Niveau des adversaires virtuels", 0, 1, 0.05),
        ("joueurs_virtuels", "Joueurs virtuels (test, boutons)", 0, 4, 1),
        ("ecart_stereo", "Écart stéréo des joueurs", 0, 1, 0.05),
        ("trinquer_pour_lancer", "Trinquer pour lancer la partie", "bool"),
        ("fenetre_trinque", "Tolérance trinquer (s)", 0.02, 0.3, 0.01),
        ("annonce_score", "Annoncer le score (voix)", "bool"),
        ("rappel_service", "Rappel service (s)", 2, 30, 1),
    ]),
    ("Wiimotes", "manette", [
        ("pilote", "Pilote (redémarrer après changement)", "choix",
         [["auto", "Automatique"], ["evdev", "evdev (Linux / Pi)"], ["hidapi", "hidapi (Mac / Windows / DolphinBar)"]]),
        ("seuil_coup", "Seuil de frappe (g)", 0.5, 3, 0.05),
        ("force_max", "Force max (g)", 1.5, 5, 0.1),
        ("refractaire", "Délai entre deux coups (s)", 0.1, 1, 0.05),
        ("seuil_choc", "Seuil choc trinquer", 0.8, 4, 0.05),
        ("vibreur_coup", "Vibreur frappe (ms)", 0, 400, 10),
        ("vibreur_faute", "Vibreur faute (ms)", 0, 1500, 10),
        ("vibreur_approche", "Petite vibration à l'approche", "bool"),
    ]),
    ("Son des téléphones", "telephone", [
        ("sabre_sur_telephone", "Sabre joué par le téléphone (sinon par l'ordinateur)", "bool"),
        ("volume_sabre", "Volume du sabre sur le téléphone", 0, 1, 0.01),
        ("transposition", "Transposition du sabre (octaves, petit haut-parleur)", 0, 4, 1),
        ("sensibilite_sabre", "Sensibilité du sabre (g pour le son maximum)", 1, 20, 0.25),
        ("son_impact", "« Toc » d'impact sur le téléphone", "bool"),
        ("volume_impact", "Volume du « toc »", 0, 1, 0.01),
    ]),
    ("Téléphones (gestes)", "telephone", [
        ("seuil_coup", "Seuil de frappe (g)", 0.5, 4, 0.05),
        ("force_max", "Seuil de force max (g) : geste pour atteindre 100 %", 2, 60, 0.5),
        ("refractaire", "Délai entre deux coups (s)", 0.1, 1, 0.05),
        ("seuil_choc", "Seuil choc trinquer (cogner deux téléphones)", 0.3, 6, 0.05),
        ("fenetre_trinque", "Tolérance trinquer entre téléphones (s)", 0.05, 0.8, 0.01),
    ]),
    ("Physique", "physique", [
        ("vitesse_max", "Vitesse max (m/s)", 3, 25, 0.5),
        ("vitesse_min", "Vitesse min (m/s)", 0.5, 10, 0.5),
        ("courbe_force", "Courbe de force (1 = linéaire, + = plus d'écart doux/fort)", 0.5, 3, 0.05),
        ("transfert", "Rebond de la vitesse reçue", 0, 1, 0.05),
        ("fenetre", "Fenêtre de frappe (m)", 0.3, 8, 0.1),
        ("moment_parfait", "Frappe parfaite : moment (s, 0 = quand la balle arrive, + = avant)", -0.2, 0.4, 0.01),
        ("tolerance_parfait_s", "Frappe parfaite : tolérance (± s)", 0.02, 0.4, 0.01),
        ("retard_max", "Délai de grâce après l'arrivée de la balle (s)", 0, 0.6, 0.01),
        ("bonus_parfait", "Frappe parfaite : multiplicateur de vitesse", 1, 4, 0.1),
        ("tension_debut", "Montée de tension à l'approche (m)", 1, 15, 0.5),
        ("ralenti", "Frappe lente : le jeu ralentit (0 = non, 1 = beaucoup)", 0, 1, 0.05),
        ("seuil_lent", "Frappe lente : en dessous de … de force, le combo se calme", 0, 1, 0.05),
        ("longueur_elastique", "Jokari : longueur de l'élastique au repos (m)", 1, 15, 0.5),
        ("raideur", "Jokari : raideur de l'élastique", 0.2, 5, 0.05),
        ("etirement_max", "Jokari : étirement avant durcissement (m)", 2, 30, 0.5),
        ("rebond_elastique", "Jokari : élan rendu par l'élastique très tendu", 0, 1, 0.05),
        ("mur_distance", "Pelote : distance du mur (m)", 3, 40, 0.5),
        ("frottement", "Pelote : frottement", 0, 0.5, 0.01),
        ("frein", "Pelote : freinage (balle courte)", 0, 2, 0.05),
        ("restitution", "Pelote : rebond du mur", 0.3, 1.2, 0.05),
        ("vitesse_retour_min", "Pelote : vitesse retour min", 0.5, 8, 0.25),
    ]),
    ("Son de la balle", "balle", [
        ("frequence", "Fréquence (Hz)", 30, 400, 1),
        ("desaccord", "Désaccord", 0, 3, 0.05),
        ("fm", "Modulation FM", 0, 5, 0.05),
        ("grain", "Saturation", 0, 1, 0.01),
        ("vibrato", "Vitesse du moteur (Hz)", 0.5, 30, 0.5),
        ("volume", "Volume", 0, 1, 0.01),
        ("filtre_pres", "Filtre proche (Hz)", 500, 16000, 100),
        ("filtre_loin", "Filtre lointain (Hz)", 80, 4000, 10),
        ("reverb_pres", "Réverb proche", 0, 1, 0.01),
        ("reverb_loin", "Réverb lointaine", 0, 1, 0.01),
        ("attenuation", "Atténuation distance", 0, 1, 0.01),
        ("doppler", "Quantité de Doppler", 0, 3, 0.05),
        ("vitesse_son", "Vitesse du son virtuelle", 5, 340, 1),
        ("tension", "Climax d'approche", 0, 3, 0.05),
        ("depart_grave", "Hauteur au départ du combo (demi-tons)", -24, 0, 0.5),
        ("montee_combo", "Montée vers l'aigu au combo max (demi-tons)", 0, 36, 0.5),
        ("hauteur_force", "Écart de hauteur frappe douce → forte (demi-tons)", 0, 36, 0.5),
        ("variation_force", "Variations aléatoires des frappes fortes", 0, 3, 0.05),
        ("calme_doux", "Frappe douce plus calme (moins de tension à l'approche)", 0, 1, 0.05),
        ("indicatif", "Indicatif à l'octave juste avant l'arrivée (volume, 0 = sans)", 0, 1.5, 0.05),
        ("indicatif_avance", "Indicatif : commence … s avant le bon moment", 0.1, 1.5, 0.05),
        ("souffle_retour", "Souffle « shaper » au retour (pulsations qui accélèrent)", 0, 1.5, 0.05),
        ("riser", "Riser à chaque retour (de plus en plus fort avec le combo)", "bool"),
    ]),
    ("Combo (échanges enchaînés)", "combo", [
        ("actif", "Combo activé", "bool"),
        ("echanges_max", "Échanges pour le combo maximum", 3, 40, 1),
        ("bonus_parfait", "Une frappe parfaite compte en plus", 0, 5, 1),
        ("acceleration", "Accélération au combo max (+ %)", 0, 2, 0.05),
        ("erratique", "Balle erratique (distance, vitesse, espace)", 0, 2, 0.05),
        ("couches", "Couches de son ajoutées", 0, 1.5, 0.05),
        ("annonce_tous", "Annonce vocale tous les … (0 = jamais)", 0, 20, 1),
        ("raideur_combo", "Élastique plus raide au combo max (+ ×)", 0, 3, 0.05),
    ]),
    ("Dubstep (style Lux Cache)", "dubstep", [
        ("wobble", "Wobble de la balle (0 conseillé : il brouille la distance et la vitesse)", 0, 1.5, 0.05),
    ]),
    ("Mode musical", "musical", [
        ("actif", "Mode musical : un beat accompagne la partie et s'étoffe avec le combo", "bool"),
        ("bpm", "Tempo (bpm)", 80, 180, 1),
        ("volume", "Volume du beat", 0, 1.5, 0.01),
    ]),
    ("Arpégiateur (entre avec le combo)", "arpegiateur", [
        ("actif", "Arpégiateur activé", "bool"),
        ("seuil", "Niveau de combo où il entre (0 = tout de suite, 1 = combo max)", 0, 1, 0.05),
        ("volume", "Volume", 0, 1.5, 0.01),
        ("tempo", "Tempo de base (notes/s, accélère avec le combo)", 1, 16, 0.5),
        ("octave", "Octave au-dessus de la balle", -1, 3, 1),
        ("motif", "Motif", "choix", [[0, "Mineur (montant / descendant)"], [1, "Majeur"], [2, "Quintes"], [3, "Aléatoire"]]),
        ("reverb", "Réverb", 0, 1, 0.01),
    ]),
    ("Sabres (son de chaque joueur)", "sabre", [
        ("frequence", "Fréquence joueur 1 (Hz)", 30, 300, 1),
        ("ecart_joueurs", "Écart entre joueurs (demi-tons)", 0, 12, 1),
        ("volume", "Volume", 0, 1, 0.01),
        ("brillance", "Brillance", 0, 2, 0.05),
        ("grain", "Grésillement", 0, 1, 0.01),
        ("repos", "Niveau au repos", 0, 1, 0.01),
        ("reverb", "Réverb", 0, 1, 0.01),
    ]),
] + [
    (f"Son : {k}", f"sons.{k}", [
        ("sample", "Sample", "sample"),
        ("hauteur", "Hauteur (demi-tons)", -24, 24, 0.5),
        ("hauteur_random", "Hauteur aléatoire ±", 0, 12, 0.25),
        ("hauteur_force", "Hauteur selon la force", -12, 12, 0.5),
        ("volume", "Volume (dB)", -30, 6, 0.5),
        ("volume_force", "Volume selon la force (dB)", 0, 30, 0.5),
        ("volume_random", "Volume aléatoire ± dB", 0, 12, 0.5),
        ("filtre_random", "Filtre aléatoire", 0, 1, 0.05),
        ("reverb", "Réverb", 0, 1, 0.01),
    ]) for k in SOUND_KINDS
] + [
    ("Réverb", "reverb", [("taille", "Taille réverb", 0, 1, 0.01), ("amorti", "Amorti réverb", 0, 1, 0.01)]),
    ("Son de l'ordinateur", "general", [
        ("sortie_audio", "Sortie audio (enceinte Bluetooth, haut-parleurs…)", "sortie"),
        ("style", "Style sonore", "choix", [["", "Classique (synthés intégrés)"]] + list_kits()),
        ("volume", "Volume général", 0, 1.5, 0.01),
    ]),
    ("Réseau (QR codes)", "reseau", [
        ("wifi_nom", "Nom du Wi-Fi", "texte"),
        ("wifi_mdp", "Mot de passe du Wi-Fi", "texte"),
        ("wifi_securite", "Sécurité", "choix", [["WPA", "WPA / WPA2 / WPA3"], ["WEP", "WEP"], ["nopass", "Sans mot de passe"]]),
        ("adresse", "Adresse de la machine dans le QR code (vide = son adresse IP)", "texte"),
    ]),
]


def clamp(x, a, b):
    return a if x < a else b if x > b else x


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        elif k in out:
            out[k] = v
    return out


# Grandes familles de la page de réglages (titres de SCHEMA ; « Son : … » va dans Son)
FAMILLES = [
    ("🎮 Partie", ["Jeu", "Mode musical", "Combo (échanges enchaînés)", "Physique"]),
    ("📱 Téléphones et manettes", ["Téléphones (gestes)", "Wiimotes"]),
    ("🔊 Son", ["Son de l'ordinateur", "Dubstep (style Lux Cache)", "Son de la balle", "Arpégiateur (entre avec le combo)",
               "Sabres (son de chaque joueur)", "Son des téléphones", "Réverb", "Son : *"]),
    ("🌐 Réseau", ["Réseau (QR codes)"]),
]


def load_config(path=CONFIG_PATH):
    try:
        with open(path, encoding="utf-8") as f:
            return deep_merge(DEFAULTS, json.load(f))
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)


def list_samples():
    try:
        return sorted(f for f in os.listdir(SAMPLES_DIR) if f.lower().endswith(SAMPLE_EXT))
    except OSError:
        return []


def list_presets():
    try:
        return sorted(f[:-5] for f in os.listdir(PRESETS_DIR) if f.endswith(".json"))
    except OSError:
        return []


# ======================================================================
#  Son (SuperCollider via OSC)
# ======================================================================
class Sound:
    def __init__(self, cfg, sc_port=57120, listen_port=57130):
        self.cfg = cfg
        self.out = osc.OscClient("127.0.0.1", sc_port)
        self.ready = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", listen_port))
        self._voice_n = 0
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._hello, daemon=True).start()

    def _listen(self):
        while True:
            try:
                addr, _ = osc.decode(self.sock.recv(4096))
            except Exception:
                continue
            if addr == "/jokari/ready":
                print("[son] SuperCollider prêt")
                self.ready = True
                self._loaded = {}                    # SuperCollider (re)démarré : tout recharger
                self.push_all()

    def _hello(self):
        while True:
            if not self.ready:
                self.out.send("/jokari/hello")
            time.sleep(1.0)

    def push_all(self):
        b, s, c = self.cfg["balle"], self.cfg["sabre"], self.cfg
        self.out.send("/set", "ball", "freq", float(b["frequence"]), "detune", float(b["desaccord"]),
                      "fm", float(b["fm"]), "grit", float(b["grain"]), "wobble", float(b["vibrato"]),
                      "volume", float(b["volume"]), "tensionBoost", float(b["tension"]),
                      "low", float(b["depart_grave"]), "rise", float(b["montee_combo"]),
                      "epitch", float(b["hauteur_force"]), "evar", float(b["variation_force"]),
                      "cueVol", float(b["indicatif"]), "noiseVol", float(b["souffle_retour"]))
        A = c["arpegiateur"]
        self.out.send("/set", "arp", "freq", float(b["frequence"]), "low", float(b["depart_grave"]),
                      "rise", float(b["montee_combo"]), "volume", float(A["volume"]) if A["actif"] else 0.0,
                      "threshold", float(A["seuil"]), "rate", float(A["tempo"]), "octave", float(A["octave"]),
                      "motif", float(A["motif"]), "rev", float(A["reverb"]), "epitch", float(b["hauteur_force"]))
        self.out.send("/set", "saber", "volume", float(s["volume"]), "bright", float(s["brillance"]),
                      "buzz", float(s["grain"]), "idle", float(s["repos"]), "rev", float(s["reverb"]))
        self.out.send("/set", "reverb", "room", float(c["reverb"]["taille"]), "damp", float(c["reverb"]["amorti"]))
        self.out.send("/set", "master", "gain", float(c["general"]["volume"]))
        self.kit = load_kit(c["general"]["style"])
        D = c["dubstep"]
        dub = bool(self.kit and self.kit.get("dubstep"))
        self.out.send("/set", "ball", "dub", float(D["wobble"]) if dub else 0.0, "bpm", float(c["musical"]["bpm"]))
        # samples : choisi à la main (prioritaire) > kit du style > synthé intégré.
        # On n'envoie que ce qui change (le kit fait une quarantaine de fichiers).
        want = {}
        for k in SOUND_KINDS:
            name = c["sons"][k]["sample"]
            path = os.path.join(SAMPLES_DIR, name) if name else ""
            want[k] = path if (path and os.path.isfile(path)) else ""
        if self.kit:
            folder = self.kit["dossier"]
            for k, files in self.kit.get("sons", {}).items():
                for i, f in enumerate(files):
                    want[f"{k}#{i}"] = os.path.join(folder, f)
            for p, files in enumerate(self.kit.get("joueurs", [])):
                for i, f in enumerate(files):
                    want[f"impact#j{p}#{i}"] = os.path.join(folder, f)
            for part, files in self.kit.get("beat", {}).items():
                for i, f in enumerate(files):
                    want[f"beat_{part}#{i}"] = os.path.join(folder, f)
        loaded = getattr(self, "_loaded", {})
        for key in set(loaded) - set(want):
            self.out.send("/load", key, "")
        for key, path in want.items():
            if loaded.get(key) != path:
                self.out.send("/load", key, path if (not path or os.path.isfile(path)) else "")
        self._loaded = want
        beat = (self.kit or {}).get("beat", {})
        self.out.send("/beatkit", *[len(beat.get(x, [])) for x in ("kick", "snare", "hat")])
        if getattr(self, "_players", None):
            self.players(*self._players)

    def players(self, n, pans, muted=()):
        self._players = (n, pans, muted)
        s = self.cfg["sabre"]
        for i in range(8):
            freq = float(s["frequence"]) * 2 ** (i * float(s["ecart_joueurs"]) / 12)
            self.out.send("/saber", i, int(i < n and i not in muted), freq, float(pans[i]) if i < n else 0.0)

    def motions(self, values):
        self.out.send("/motion", *[float(v) for v in values])

    def ball(self, amp, ratio, cutoff, rev, tension, speed, pan, combo=0.0, energy=0.5, cue=0.0, approach=0.0):
        self.out.send("/ball", float(amp), float(ratio), float(cutoff), float(rev), float(tension), float(speed),
                      float(pan), float(combo), float(energy), float(cue), float(approach))

    def _kit_key(self, kind, player):
        """Round robin dans le kit : chaque son tourne sur ses variantes (par joueur pour la frappe)."""
        kit = getattr(self, "kit", None)
        if not kit or self.cfg["sons"][kind]["sample"]:
            return kind
        if kind == "impact" and kit.get("joueurs") and player is not None:
            sets = kit["joueurs"]
            p = player % len(sets)
            files, prefix = sets[p], f"impact#j{p}"
        else:
            files, prefix = kit.get("sons", {}).get(kind, []), kind
        if not files:
            return kind
        rr = getattr(self, "_rr", {})
        i = rr.get(prefix, random.randrange(len(files)))
        rr[prefix] = (i + 1) % len(files)
        self._rr = rr
        return f"{prefix}#{i}"

    def beat(self, on, level, cfg):
        """Mode musical : beat demi-tempo (samples du kit s'il en a, sinon batterie synthétisée)."""
        M = cfg["musical"]
        self.out.send("/beat", int(bool(on and M["actif"])), float(level), float(M["volume"]), float(M["bpm"]))

    def event(self, kind, pan=0.0, force=0.5, distance=0.0, dref=10.0, gain=1.0, dur=0.0, player=None):
        """Joue un son ponctuel (sample choisi, kit du style, ou synthé intégré) avec hauteur et aléa."""
        p = self.cfg["sons"][kind]
        key = self._kit_key(kind, player)
        b = self.cfg["balle"]
        semis = p["hauteur"] + random.uniform(-1, 1) * p["hauteur_random"] + p["hauteur_force"] * force
        db = p["volume"] + p["volume_force"] * (force - 0.6) + random.uniform(-1, 1) * p["volume_random"]
        amp = gain * 10 ** (db / 20) / (1 + b["attenuation"] * distance)
        cutoff = 18000 / 2 ** (random.random() * p["filtre_random"] * 5)
        dn = clamp(distance / max(dref, 0.1), 0, 1)
        if distance > 0:
            cutoff = min(cutoff, b["filtre_pres"] * (b["filtre_loin"] / b["filtre_pres"]) ** dn * 2)
        rev = max(p["reverb"], b["reverb_pres"] + (b["reverb_loin"] - b["reverb_pres"]) * dn)
        self.out.send("/play", key, float(2 ** (semis / 12)), float(amp), float(clamp(pan, -1, 1)),
                      float(cutoff), float(rev), float(dur))

    def say(self, text):
        """Annonce vocale -> fichier son -> SuperCollider, sans bloquer le jeu.
        Linux/Pi : espeak-ng · Mac : say · Windows : synthèse vocale intégrée (PowerShell)."""
        if not self.cfg["jeu"]["annonce_score"]:
            return

        def run():
            self._voice_n = (self._voice_n + 1) % 10
            base = os.path.join(tempfile.gettempdir(), f"jokari_voix_{self._voice_n}")
            lang = self.cfg["general"]["voix"]
            try:
                if sys.platform == "darwin":
                    path = base + ".aiff"
                    cmd = ["say", "-o", path, text]
                    if lang == "fr":
                        cmd[1:1] = ["-v", "Thomas"]
                elif sys.platform == "win32":
                    path = base + ".wav"
                    safe = text.replace("'", "''")
                    ps = ("Add-Type -AssemblyName System.Speech;"
                          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                          f"try{{$s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'{lang}-FR')}}catch{{}};"
                          f"$s.SetOutputToWaveFile('{path}');$s.Speak('{safe}');$s.Dispose()")
                    cmd = ["powershell", "-NoProfile", "-Command", ps]
                elif shutil.which("espeak-ng"):
                    path = base + ".wav"
                    cmd = ["espeak-ng", "-v", lang, "-s", "150", "-w", path, text]
                else:
                    return
                subprocess.run(cmd, check=True, timeout=8,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.out.send("/voice", path)
            except Exception:
                if sys.platform == "darwin" and lang == "fr":   # voix Thomas absente : voix par défaut
                    try:
                        subprocess.run(["say", "-o", path, text], check=True, timeout=8)
                        self.out.send("/voice", path)
                    except Exception:
                        pass
        threading.Thread(target=run, daemon=True).start()


# ======================================================================
#  Jeu
# ======================================================================
class Game:
    """États : attente (trinquer pour lancer) -> service -> vol -> pause -> service ... -> fin."""

    def __init__(self, cfg, sound, manager):
        self.cfg, self.sound, self.mgr = cfg, sound, manager
        self.q = queue.Queue()
        self.n = 0
        self.points = []
        self.virtual_motion = [0.0] * 64     # jusqu'à 64 joueurs
        self.state = "attente" if cfg["jeu"]["trinquer_pour_lancer"] else "service"
        self.server = 0
        self.hitter = self.receiver = 0
        self.d = self.v = 0.0
        self.apex_done = False
        self.in_window = False
        self.rally = self.best_rally = 0
        self.timers = []
        self.last_cue = 0.0
        self.chocs = {}
        self.bot_slots = []     # adversaires virtuels : derniers numéros de joueur
        self.bot_plan = None
        self.k_flight = 1.0
        self.flight_peak = self.apex_pred = 1.0
        self.stretch_max = 0.0
        self.snap_done = False
        self.v_launch = 0.0
        self.combo = 0.0
        self.erratic = (0.0, 0.0, 0.0, 1.0)   # (quantité, phase vitesse, phase pan, fréquence)
        self.flight_t = 0.0
        self.last_force = (0, 0, 0.0, 0.0)    # (compteur, joueur, force, pic en g) de la dernière frappe
        self.hits = []                        # dernières frappes (page de réglages)
        self.demo = None                      # vol de balle de test (page de réglages)
        self.demo_match = 0                   # démo de jeu : nombre de joueurs virtuels (0 = non)
        self.order = []
        self.energy = 0.5
        self.players_key = None
        self.perfect = (0, 0)   # (compteur, joueur) de la dernière frappe parfaite
        self.message = "En attente : trinquez pour lancer" if self.state == "attente" else "Service"
        self.lock = threading.Lock()

    # ---------- entrées (thread-safe) ----------
    def on_wiimote(self, w, kind, value):
        if w.slot is not None:
            self.q.put((kind, w.slot, value))

    def post(self, kind, slot=0, value=None):
        self.q.put((kind, slot, value))

    # ---------- utilitaires ----------
    def pan(self, i):
        if self.n <= 1:
            return 0.0
        s = self.cfg["jeu"]["ecart_stereo"]
        return -s + 2 * s * i / (self.n - 1)

    def dref(self):
        P = self.cfg["physique"]
        return P["mur_distance"] if self.cfg["jeu"]["mode"] == "pelote" else P["longueur_elastique"] + P["etirement_max"]

    def later(self, delay, fn):
        self.timers.append((time.monotonic() + delay, fn))

    def ev(self, kind, pan=0.0, force=0.5, distance=0.0, **kw):
        self.sound.event(kind, pan=pan, force=force, distance=distance, dref=self.dref(), **kw)

    def set_state(self, st, msg):
        self.state, self.message = st, msg
        self.last_cue = time.monotonic()

    # ---------- déroulé ----------
    def new_game(self):
        self.points = [0] * self.n
        self.rally = 0
        self.server = random.randrange(self.n) if self.n else 0
        self.timers.clear()
        self.d = self.v = 0.0
        # ordre de jeu : on frappe chacun son tour, en partant du serveur
        order = [self.name((self.server + i) % self.n) for i in range(self.n)]
        self.order = order
        self.set_state("service", f"Nouvelle partie — {self.name(self.server, True)} sert"
                       + (f" · ordre : {' → '.join(order)}" if self.n > 2 else ""))
        self.ev("service", pan=self.pan(self.server))
        # annonce vocale de l'ordre de jeu et de qui sert (au milieu du son de service)
        if self.n > 1:
            if self.n == 2:
                txt = f"{order[0]} contre {order[1]}. {order[0]} commence."
            else:
                txt = ("Ordre de jeu : " + ", puis ".join(order) + f". {order[0]} commence." if self.n <= 6
                       else f"{self.n} joueurs. {order[0]} commence.")   # 24 prénoms : trop long à dire
            self.later(0.4, lambda: self.sound.say(txt))
            if self.server in self.bot_slots:      # le bot attend la fin de l'annonce pour servir
                self.bot_plan = ("service", time.monotonic() + 2.0 + 0.9 * self.n + random.uniform(0, 1.0))
        self.rumble(self.server, 150)

    def to_lobby(self):
        self.timers.clear()
        self.set_state("attente", "En attente : trinquez pour lancer")

    def set_mode(self, mode):
        self.cfg["jeu"]["mode"] = mode
        save_config(self.cfg)
        self.sound.say("mode pelote" if mode == "pelote" else "mode jokari")
        if self.state == "vol":
            self.d = self.v = 0.0
            self.set_state("service", f"Mode {mode} — service : {self.name(self.server)}")

    def name(self, slot, cap=False):
        """Prénom du joueur (saisi sur son téléphone), « l'adversaire virtuel », ou « joueur N »."""
        r = None if self.demo_match else self.mgr.remotes.get(slot)
        n = (getattr(r, "name", "") or "").strip()
        if not n:
            n = "l'adversaire virtuel" if slot in self.bot_slots and len(self.bot_slots) == 1 else f"joueur {slot + 1}"
        return n[0].upper() + n[1:] if cap else n

    def rumble(self, slot, ms):
        if not self.demo_match:                      # démo de jeu : les raquettes ne vibrent pas
            self.mgr.rumble(slot, ms)

    def combo_level(self):
        C = self.cfg["combo"]
        return clamp(self.combo / max(C["echanges_max"], 1), 0, 1) if C["actif"] else 0.0

    def launch(self, slot, force, serve):
        P, C = self.cfg["physique"], self.cfg["combo"]
        f = clamp(force, 0.0, 1.0) ** P["courbe_force"]     # courbe : plus d'écart entre doux et fort
        v0 = P["vitesse_min"] + (P["vitesse_max"] - P["vitesse_min"]) * f
        mult, parfait = 1.0, False
        if not serve:
            v0 += P["transfert"] * abs(self.v) * f        # une frappe douce n'hérite pas de la vitesse reçue
            self.rally += 1
            self.best_rally = max(self.best_rally, self.rally)
            # timing : plus on frappe près du point idéal, plus la balle repart vite
            # timing mesuré en temps : tau = secondes avant que la balle n'arrive sur le joueur
            # (négatif = après, dans le délai de grâce). Le parfait est calé sur l'arrivée entendue.
            tau = self.d / max(abs(self.v), 0.1)
            q = clamp(1 - abs(tau - P["moment_parfait"]) / max(P["tolerance_parfait_s"], 0.01), 0, 1)
            mult = 1 + (P["bonus_parfait"] - 1) * q * q
            parfait = q >= 0.6
            before = int(self.combo)
            if f < P["seuil_lent"]:                          # frappe lente : le jeu se calme
                self.combo *= 1 - P["ralenti"] * (1 - f / max(P["seuil_lent"], 0.01))
            self.combo += 1 + (C["bonus_parfait"] if parfait else 0)
            step = max(int(C["annonce_tous"]), 0)
            if C["actif"] and step and int(self.combo) // step > before // step:
                self.sound.say(f"combo {int(self.combo) // step * step}")
        else:
            self.rally = 0
            self.combo = 0.0
            self.d = 0.3
        L = self.combo_level()
        mult *= 1 + C["acceleration"] * L                      # le combo accélère le jeu
        self.v = self.v_launch = min(v0 * mult, P["vitesse_max"] * 1.3 * mult)
        self.d = max(self.d, 0.3)
        g = clamp((self.v - P["vitesse_min"]) / max(P["vitesse_max"] - P["vitesse_min"], 0.1), 0, 1.3)
        # Jokari : vol libre jusqu'à la longueur de l'élastique, puis il se tend et la ramène.
        # Plus on frappe fort, plus il s'étire, plus il tire (il durcit) : la balle revient plus tôt
        # et plus fort. Le combo raidit l'élastique ; l'erratique rend sa raideur imprévisible.
        E = C["erratique"] * L
        self.k_flight = P["raideur"] * (1 + C["raideur_combo"] * L) * random.uniform(1 - 0.35 * E, 1 + 0.5 * E)
        # frappe douce : l'élastique se détend, la balle flotte et revient plus tard
        self.k_flight *= 1 - P["ralenti"] * 0.6 * (1 - clamp(g, 0, 1))
        self.stretch_max = 0.0
        self.snap_done = False
        self.erratic = (E, random.uniform(0, 6.28), random.uniform(0, 6.28), random.uniform(0.5, 1.1))
        self.flight_t = 0.0
        self.flight_peak = self.d
        self.apex_pred = self.predict_apex()
        self.energy = clamp(g, 0, 1.3)              # énergie de la frappe : colore tout le vol
        self.hitter = slot
        self.receiver = (slot + 1) % max(self.n, 1)
        self.apex_done = self.in_window = False
        r = None if self.demo_match else self.mgr.remotes.get(slot)
        peak = getattr(getattr(r, "det", None), "last_peak", 0.0)
        self.last_force = (self.last_force[0] + 1, slot, force, peak)
        self.hits = (self.hits + [{"nom": self.name(slot, True), "joueur": slot + 1, "force": round(force, 2),
                                   "pic": round(peak, 1), "parfait": parfait, "service": serve}])[-14:]
        vib = self.cfg["manette"]["vibreur_coup"] * (0.6 + 1.8 * f)   # vibreur selon la force
        if parfait:
            self.perfect = (self.perfect[0] + 1, slot)
            self.set_state("vol", f"Frappe parfaite ! {self.name(slot, True)} → {self.name(self.receiver)}")
            self.ev("parfait", pan=self.pan(slot), force=1.0)
            self.rumble(slot, vib * 2.5)
        else:
            combo = f" — combo {int(self.combo)}" if C["actif"] and self.combo >= 2 else ""
            self.set_state("vol", f"{self.name(slot, True)} frappe → {self.name(self.receiver)}{combo}")
            self.rumble(slot, vib)
        self.ev("impact", pan=self.pan(slot), force=f, player=slot)

    def fault(self, slot, reason):
        self.d = self.v = 0.0
        self.combo = 0.0
        self.ev("faute", pan=self.pan(slot))
        self.rumble(slot, self.cfg["manette"]["vibreur_faute"])
        if self.n <= 1:
            msg = f"Raté ! Série : {self.rally} (record {self.best_rally})"
            self.set_state("pause", msg)
            serie = self.rally
            self.later(1.2, lambda: self.sound.say(f"série de {serie}"))
            self.later(2.5, lambda: self.set_state("service", "Service"))
            self.server = 0
            return
        winner = self.hitter if (self.hitter != slot) else (slot + 1) % self.n
        self.points[winner] += 1
        self.server = winner
        self.set_state("pause", f"Point pour {self.name(winner)} ({reason} : {self.name(slot)})")

        def announce():
            self.ev("point", pan=self.pan(winner))
            if self.points[winner] >= self.cfg["jeu"]["points_victoire"]:
                self.later(0.8, lambda: self.win(winner))
            else:
                self.sound.say(f"Point pour {self.name(winner)}")   # le score s'affiche sur les téléphones
                self.later(2.0, lambda: self.set_state("service", f"Service : {self.name(winner)}"))
        self.later(1.0, announce)

    def win(self, winner):
        self.ev("victoire", pan=self.pan(winner))
        self.rumble(winner, 800)
        who = self.name(winner)                    # le nom du gagnant, par-dessus la musique de victoire
        bravo = f"{who} gagne !" if who.startswith(("l'", "joueur")) else f"Bravo {who}, tu gagnes !"
        self.later(0.9, lambda: self.sound.say(bravo))
        self.set_state("fin", f"Victoire : {self.name(winner, True)} !")
        if self.cfg["jeu"]["trinquer_pour_lancer"]:
            self.later(4.0, self.to_lobby)
        else:
            self.later(6.0, self.new_game)

    def trinque(self, slots):
        self.ev("trinque", pan=0.0, force=0.5)
        for s in slots:
            self.rumble(s, 200)
        self.later(0.7, self.new_game)
        self.set_state("pause", "Tchin ! La partie commence…")

    # ---------- traitement des événements ----------
    def handle(self, kind, slot, value):
        if kind == "coup":
            if slot not in self.mgr.remotes:   # joueur virtuel : simule le geste pour le sabre
                self.virtual_motion[slot % 8] = max(self.virtual_motion[slot % 8], 0.5 + value * 2.5)
            if slot >= self.n:
                return
            if self.demo:                       # vol de test en cours : on ne joue pas
                return
            if self.state == "service" and slot == self.server:
                self.launch(slot, value, serve=True)
            elif self.state == "vol" and slot == self.receiver and self.v < 0 \
                    and self.d <= self.cfg["physique"]["fenetre"]:
                self.launch(slot, value, serve=False)
        elif kind in ("choc", "tchin"):   # tchin : bouton du téléphone, tolérance d'une seconde
            if self.state not in ("attente", "fin") or slot >= self.n:
                return
            self.chocs[slot] = value
            def tol(sl):                  # les téléphones ont leur propre tolérance (paquets, Wi-Fi)
                r = self.mgr.remotes.get(sl)
                return self.cfg["telephone"]["fenetre_trinque"] if hasattr(r, "take_vibration") \
                    else self.cfg["jeu"]["fenetre_trinque"]
            partners = [s for s, t in self.chocs.items() if s != slot
                        and abs(t - value) <= (1.0 if kind == "tchin" else max(tol(slot), tol(s)))]
            partners += [s for s in self.bot_slots if s != slot]   # un adversaire virtuel trinque toujours
            if partners:
                self.chocs.clear()
                self.trinque([slot] + partners)
        elif kind == "bouton":
            if value == "home":
                self.new_game()
            elif value in ("plus", "moins"):
                self.set_mode("pelote" if self.cfg["jeu"]["mode"] == "jokari" else "jokari")
        elif kind == "test":
            self.test_sound(value)
        elif kind == "action":
            name = value
            if name == "nouvelle_partie":
                self.new_game()
            elif name == "attente":
                self.to_lobby()
            elif name == "mode":
                self.set_mode("pelote" if self.cfg["jeu"]["mode"] == "jokari" else "jokari")
            elif name == "musical":           # bouton de la page de réglages : mode musical oui / non
                on = not self.cfg["musical"]["actif"]
                self.cfg["musical"]["actif"] = on
                save_config(self.cfg)
                self.sound.say("mode musical" if on else "sans musique")
            elif name == "adversaire":    # bouton du téléphone : avec / sans adversaire virtuel
                on = not self.cfg["jeu"]["adversaires_virtuels"]
                self.cfg["jeu"]["adversaires_virtuels"] = int(on)
                save_config(self.cfg)
                self.sound.say("adversaire virtuel" if on else "sans adversaire virtuel")
                if on and self.state in ("attente", "fin"):   # seul contre l'ordi : la partie démarre
                    self.later(1.6, lambda: self.trinque([0]) if self.state in ("attente", "fin") else None)
            elif name == "trinquer":
                if self.state in ("attente", "fin") and self.n:
                    self.trinque(list(range(min(self.n, 2))))
            elif name.startswith("test:"):
                k = name[5:]
                if k in SOUND_KINDS:
                    self.ev(k, pan=0.0, force=0.7)

    # ---------- boucle ----------
    def update_players(self):
        if self.demo_match:                          # démo de jeu : que des joueurs virtuels
            n = self.demo_match
            self.bot_slots = list(range(n))
        else:
            base = max([s + 1 for s in self.mgr.remotes] + [int(self.cfg["jeu"]["joueurs_virtuels"])])
            n = max(base + int(self.cfg["jeu"]["adversaires_virtuels"]), 1)
            self.bot_slots = list(range(base, n)) if self.cfg["jeu"]["adversaires_virtuels"] else []
        if n != self.n:
            self.n = n
            self.points = (self.points + [0] * n)[:n]
            self.server %= n
            if self.state == "vol":
                self.d = self.v = 0.0
                self.set_state("service", f"{n} joueur(s) — service : {self.name(self.server)}")
        muted = frozenset(s for s, r in self.mgr.remotes.items() if hasattr(r, "take_vibration")) \
            if self.cfg["telephone"]["sabre_sur_telephone"] and not self.demo_match else frozenset()
        if (n, muted) != self.players_key:          # sabre des téléphones : joué par le téléphone
            self.players_key = (n, muted)
            self.sound.players(n, [self.pan(i) for i in range(n)] + [0.0] * 8, muted)

    def step(self, dt):
        now = time.monotonic()
        with self.lock:
            self.update_players()
            while True:
                try:
                    kind, slot, value = self.q.get_nowait()
                except queue.Empty:
                    break
                if self.demo_match and kind in ("coup", "choc", "tchin", "bouton"):
                    continue                         # démo de jeu : les raquettes ne jouent pas
                self.handle(kind, slot, value)
            for t in [t for t in self.timers if t[0] <= now]:
                self.timers.remove(t)
                t[1]()
            if self.state == "vol":
                self.physics(dt)
            self.bots(now)
            if self.state == "service" and now - self.last_cue > self.cfg["jeu"]["rappel_service"]:
                self.last_cue = now
                self.ev("service", pan=self.pan(self.server))
            self.send_sound()

    def test_sound(self, b):
        """Écouter un son depuis la page de réglages, à la force et au niveau de combo voulus."""
        t = b.get("action", "")
        f = clamp(float(b.get("force", 0.6)), 0, 1)
        L = clamp(float(b.get("combo", 0)), 0, 1)
        fc = f ** self.cfg["physique"]["courbe_force"]
        j = max(int(b.get("joueur", 1)) - 1, 0)
        if t == "test_frappe":
            self.ev("impact", pan=self.pan(j) if j < self.n else 0.0, force=fc, player=j)
        elif t == "test_parfait":
            self.ev("parfait", pan=0.0, force=1.0)
            self.ev("impact", pan=0.0, force=fc, player=j)
        elif t == "test_riser":
            self.ev("riser", pan=0.0, force=max(L, 0.3), gain=0.25 + 0.75 * max(L, 0.3), dur=2.0)
        elif t == "test_voix":
            self.sound.say(f"Point pour {self.name(0)}")
        elif t == "test_demo":                        # démo de jeu : marche / arrêt
            self.demo_match = 0 if self.demo_match else clamp(int(b.get("joueurs", 2)), 2, 4)
            self.chocs.clear()
            self.to_lobby()                            # que des bots : ils trinquent et jouent tout seuls
            self.message = (f"Démo de jeu : {self.demo_match} joueurs virtuels" if self.demo_match
                            else "Démo arrêtée — en attente : trinquez pour lancer")
        elif t == "test_vol" and self.state in ("attente", "fin", "service") and not self.demo:
            # un vrai vol de balle (aller, élastique ou mur, retour), sans marquer de point
            self.demo = (self.state, self.message, self.combo)
            self.launch(0, f, serve=True)
            self.combo = L * max(self.cfg["combo"]["echanges_max"], 1)
            self.message = f"Test : vol de balle (force {round(f * 100)} %, combo {round(L * 100)} %)"

    def end_demo(self):
        st, msg, combo = self.demo
        self.demo = None
        self.d = self.v = 0.0
        self.state, self.message, self.combo = st, msg, combo
        self.last_cue = time.monotonic()

    def bots(self, now):
        """Adversaires virtuels : servent après un temps de réflexion, renvoient à un moment
        aléatoire dans la fenêtre de frappe, et ratent parfois selon leur niveau."""
        if not self.bot_slots or self.demo:
            self.bot_plan = None
            return
        lvl = clamp(self.cfg["jeu"]["niveau_adversaire"], 0, 1)
        force = lambda: clamp(random.gauss(0.4 + 0.4 * lvl, 0.15), 0.1, 1.0)
        if self.demo_match:                          # démo : bon niveau, frappes de toutes les forces
            lvl = 0.85
            force = lambda: random.choice([random.uniform(0.02, 0.3), random.uniform(0.3, 0.7), random.uniform(0.7, 1.0)])
        plan = self.bot_plan
        if self.state == "service" and self.server in self.bot_slots:
            if plan is None or plan[0] != "service":
                self.bot_plan = ("service", now + random.uniform(1.2, 2.8))
            elif now >= plan[1]:
                self.bot_plan = None
                self.handle("coup", self.server, force())
        elif self.state == "vol" and self.receiver in self.bot_slots and self.v < 0:
            if plan is None or plan[0] != "retour":
                P = self.cfg["physique"]
                W = P["fenetre"]
                fast = clamp(self.v_launch / P["vitesse_max"] - 1, 0, 1)   # balle survitaminée : plus dure
                ok = random.random() < (0.35 + 0.62 * lvl) * (1 - 0.4 * fast)
                if not ok:
                    target = ("rate", 0.0)
                elif random.random() < 0.3 * lvl:                       # le bot tente la parfaite
                    target = ("t", P["moment_parfait"] + random.uniform(-0.5, 0.5) * P["tolerance_parfait_s"])
                else:
                    target = ("d", random.uniform(0.1, 0.95) * W)
                self.bot_plan = plan = ("retour", target)
            kind, val = plan[1]
            tau = self.d / max(abs(self.v), 0.1)
            if (kind == "d" and self.d <= val) or (kind == "t" and tau <= val):
                self.bot_plan = None
                self.handle("coup", self.receiver, force())
        elif self.state == "attente" and len(self.bot_slots) == self.n and self.n > 1:
            # que des adversaires virtuels (démo / réglage du son) : ils lancent la partie seuls
            if plan is None or plan[0] != "attente":
                self.bot_plan = ("attente", now + 2.0)
            elif now >= plan[1]:
                self.bot_plan = None
                self.trinque(list(self.bot_slots))
        else:
            self.bot_plan = None

    def predict_apex(self):
        """Distance la plus lointaine que la balle atteindra (pour la phase du vol)."""
        P = self.cfg["physique"]
        if self.cfg["jeu"]["mode"] == "pelote":
            return P["mur_distance"]
        L0, S = P["longueur_elastique"], max(P["etirement_max"], 0.1)
        d, v = self.d, self.v
        for _ in range(3000):
            if v <= 0:
                break
            x = d - L0
            if x > 0:
                v -= self.k_flight * x * (1 + (x / S) ** 2) * 0.01
            d += v * 0.01
        return max(d, 0.5)

    def phase(self):
        """Phase du vol : 0 = frappe, 0,5 = élastique / mur, 1 = arrivée chez le joueur suivant."""
        if self.state != "vol":
            return None
        if self.v > 0:
            return 0.5 * clamp(self.d / max(self.apex_pred, 0.1), 0, 1)
        return 1 - 0.5 * clamp(self.d / max(self.flight_peak, 0.1), 0, 1)

    def arrival_time(self):
        """Jokari : temps restant avant que la balle n'arrive sur le joueur (sans l'aléa erratique)."""
        P = self.cfg["physique"]
        L0, S = P["longueur_elastique"], max(P["etirement_max"], 0.1)
        d, v, snap, t = self.d, self.v, self.snap_done, 0.0
        while d > 0 and t < 15:
            x = d - L0
            if x > 0:
                v -= self.k_flight * x * (1 + (x / S) ** 2) * 0.01
            d += v * 0.01
            if not snap and d <= L0:
                snap = True
                v *= 1 + P["rebond_elastique"] * clamp(self.stretch_max / S, 0, 1)
            t += 0.01
        return t

    def riser(self, dur):
        """Riser : monte jusqu'à l'arrivée de la balle ; plus fort et plus aigu avec le combo."""
        if not self.cfg["balle"]["riser"] or dur < 0.3:
            return
        L = self.combo_level()
        if L <= 0:
            return
        self.ev("riser", pan=self.pan(self.receiver) * 0.6, force=L, gain=0.25 + 0.75 * L, dur=dur)

    def physics(self, dt):
        P = self.cfg["physique"]
        pelote = self.cfg["jeu"]["mode"] == "pelote"
        # combo : la balle a des à-coups de vitesse (le temps de vol devient imprévisible)
        self.flight_t += dt
        E, ph, _, fr = self.erratic
        if E > 0:
            dt *= 1 + 0.45 * E * math.sin(6.283 * fr * self.flight_t + ph) * math.sin(2.1 * self.flight_t + ph * 0.7)
        if pelote:
            W = P["mur_distance"]
            if self.v > 0:
                self.v -= (P["frottement"] * self.v + P["frein"]) * dt
                if self.v <= 0.2:
                    if self.demo:
                        self.end_demo()
                    else:
                        self.fault(self.hitter, "balle courte")
                    return
            else:
                self.v *= (1 - P["frottement"] * dt)
                self.v = min(self.v, -P["vitesse_retour_min"])
            self.d += self.v * dt
            self.flight_peak = max(self.flight_peak, self.d)
            if self.v > 0 and self.d >= W:
                self.d = W - (self.d - W)
                self.v = -self.v * P["restitution"]
                self.ev("mur", pan=0.0, force=clamp(-self.v / P["vitesse_max"], 0, 1), distance=W)
                self.riser(self.d / max(abs(self.v), 0.5))
        else:
            L0, S = P["longueur_elastique"], max(P["etirement_max"], 0.1)
            x = self.d - L0
            if x > 0:                                  # élastique tendu, de plus en plus raide
                self.v -= self.k_flight * x * (1 + (x / S) ** 2) * dt
                self.stretch_max = max(self.stretch_max, x)
            self.d += self.v * dt
            self.flight_peak = max(self.flight_peak, self.d)
            if not self.apex_done and self.v <= 0:
                self.apex_done = True
                self.ev("elastique", pan=0.0, distance=self.d, force=clamp(self.stretch_max / S, 0, 1))
                self.riser(self.arrival_time())
            if self.apex_done and not self.snap_done and self.d <= L0:
                self.snap_done = True                  # l'élastique se relâche : il rend de l'élan
                self.v *= 1 + P["rebond_elastique"] * clamp(self.stretch_max / S, 0, 1)
        if self.v < 0 and self.d <= P["fenetre"] and not self.in_window:
            self.in_window = True
            if self.cfg["manette"]["vibreur_approche"]:
                self.rumble(self.receiver, 40)
        if self.v < 0 and self.d <= -P["retard_max"] * abs(self.v):   # délai de grâce dépassé
            if self.demo:                                              # vol de test : fini, sans point
                self.end_demo()
            else:
                self.fault(self.receiver, "raté")

    def ball_params(self):
        b, P = self.cfg["balle"], self.cfg["physique"]
        if self.state != "vol":
            return 0.0, 1.0, b["filtre_loin"], 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0
        d = max(self.d, 0.0)
        dn = clamp(d / max(self.dref(), 0.1), 0, 1)
        amp = 1 / (1 + b["attenuation"] * d)
        c = b["vitesse_son"]
        ratio = clamp((c / max(c + self.v, 1.0)) ** b["doppler"], 0.25, 4.0)
        cutoff = b["filtre_pres"] * (b["filtre_loin"] / b["filtre_pres"]) ** math.sqrt(dn)
        rev = b["reverb_pres"] + (b["reverb_loin"] - b["reverb_pres"]) * dn
        tension = clamp(1 - d / max(P["tension_debut"], 0.1), 0, 1) ** 1.5 if self.v < 0 else 0.0
        # frappe douce : approche calme (peu de tension, le moteur n'accélère presque pas)
        tension *= 1 - b["calme_doux"] * (1 - clamp(self.energy, 0, 1))
        speed = abs(self.v) / P["vitesse_max"]
        who = self.hitter if self.v > 0 else self.receiver
        pan = self.pan(who) * (1 - dn)
        # combo : la balle se balade dans l'espace quand elle est loin, et se recale en approchant
        E, _, php, fr = self.erratic
        if E > 0:
            pan += 0.9 * E * dn * math.sin(6.283 * 0.45 * fr * self.flight_t + php)
        # indicatif à l'octave : monte pendant `indicatif_avance` s avant le moment idéal, puis s'efface
        cue = 0.0
        if self.v < 0:
            tau = self.d / max(abs(self.v), 0.1)
            m0 = P["moment_parfait"]
            cue = clamp(1 - (tau - m0) / max(b["indicatif_avance"], 0.05), 0, 1) if tau >= m0 \
                else clamp(1 - (m0 - tau) / 0.15, 0, 1)
        # enveloppes de vol (Studio son) : volume ×, filtre en octaves, hauteur en demi-tons, réverb +
        ph, Env = self.phase() or 0.0, self.cfg["enveloppes"]
        amp *= max(envelope(Env["volume"], ph), 0)
        cutoff = clamp(cutoff * 2 ** envelope(Env["filtre"], ph), 40, 18000)
        ratio *= 2 ** (envelope(Env["hauteur"], ph) / 12)
        rev = clamp(rev + envelope(Env["reverb"], ph), 0, 1)
        return (amp, ratio, cutoff, rev, tension, speed, clamp(pan, -1, 1),
                self.combo_level() * self.cfg["combo"]["couches"], self.energy, cue,
                (1 - dn) if self.v < 0 else 0.0)          # approche : 0 au loin -> 1 sur le joueur

    def send_sound(self):
        self.sound.ball(*self.ball_params())
        mot = []
        for i in range(self.n):
            m = self.mgr.motion(i)
            if m is None:
                self.virtual_motion[i] *= 0.9
                m = self.virtual_motion[i]
            mot.append(clamp(m / max(self.cfg["manette"]["force_max"] * 0.6, 0.1), 0, 1.5))
        self.sound.motions(mot)
        # beat dubstep : tourne pendant la partie, s'étoffe avec le combo
        self.sound.beat(self.state in ("service", "vol", "pause") and self.n > 0, self.combo_level(), self.cfg)

    def snapshot(self):
        with self.lock:
            return {"etat": self.state, "message": self.message, "mode": self.cfg["jeu"]["mode"],
                    "joueurs": self.n, "points": list(self.points),
                    "manettes": sorted(s + 1 for s in self.mgr.remotes),
                    "distance": round(self.d, 2), "vitesse": round(self.v, 2),
                    "serveur": self.server + 1, "receveur": self.receiver + 1,
                    "serie": self.rally, "record": self.best_rally, "son_pret": self.sound.ready,
                    "adversaires": [s + 1 for s in self.bot_slots],
                    "parfait": [self.perfect[0], self.perfect[1] + 1],
                    "combo": int(self.combo) if self.cfg["combo"]["actif"] else 0,
                    "force": [self.last_force[0], self.last_force[1] + 1, round(self.last_force[2], 2),
                              round(self.last_force[3], 1)],
                    "noms": [self.name(i, True) for i in range(self.n)],
                    "frappes": list(self.hits), "ordre": list(self.order), "demo": self.demo_match, "phase": self.phase(),
                    "frappeur": self.hitter + 1, "dref": round(self.dref(), 2),
                    "elastique": self.cfg["physique"]["longueur_elastique"]}


# ======================================================================
#  Configuration / page web
# ======================================================================
def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CONFIG_PATH)


def envelope(points, x):
    """Valeur d'une enveloppe (segments droits entre les points) à la phase x."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * clamp((x - x0) / max(x1 - x0, 1e-6), 0, 1)
    return points[-1][1]


def set_path(cfg, path, value):
    keys = path.split(".")
    ref, dref = cfg, DEFAULTS
    for k in keys[:-1]:
        ref, dref = ref[k], dref[k]
    k = keys[-1]
    if k not in dref:
        raise KeyError(path)
    default = dref[k]
    if isinstance(default, bool):
        value = value in (True, 1, "1", "true", "on")
    elif isinstance(default, int):
        value = int(round(float(value)))
    elif isinstance(default, float):
        value = float(value)
    elif isinstance(default, list):                  # enveloppe : 2 à 16 points (phase 0..1, valeur)
        pts = sorted([clamp(float(x), 0, 1), clamp(float(y), -24, 24)] for x, y in value)[:16]
        if len(pts) < 2:
            raise ValueError("une enveloppe a au moins 2 points")
        pts[0][0], pts[-1][0] = 0.0, 1.0
        value = pts
    else:
        value = str(value)
        if k == "sample":
            value = os.path.basename(value)
    ref[k] = value


BORNE = "192.168.4.1"          # borne Wi-Fi ESP32 (esp32-wifi/)


def announce_to_hub():
    """Sur le réseau de la borne ESP32, le jeu s'y signale toutes les 2 s : la borne renvoie
    alors http://192.168.4.1 vers la page raquette, quelle que soit l'adresse de l'ordinateur."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        if local_ip().startswith(BORNE[:-1]):
            try:
                sock.sendto(b"SONICJOKARI", (BORNE, 4210))
            except OSError:
                pass
        time.sleep(2)


def qr_targets(app):
    """Adresse fixe de la raquette + texte du QR code Wi-Fi (vide si le Wi-Fi n'est pas renseigné)."""
    R = app.cfg["reseau"]
    host = R["adresse"].strip() or app.ip          # adresse IP (le nom .local ne marche pas partout)
    url = f"https://{host}:{app.https_port}/raquette"
    if not R["adresse"].strip() and (app.ip.startswith(BORNE[:-1]) or R["wifi_nom"] == "SonicJokari"):
        url = f"http://{BORNE}/"                    # borne ESP32 : adresse fixe, elle renvoie vers le jeu
    wifi = qr.wifi_text(R["wifi_nom"], R["wifi_mdp"], R["wifi_securite"]) if R["wifi_nom"].strip() else ""
    return url, wifi


def save_qr_files(app):
    """Enregistre les QR codes en PNG dans qr/ (à imprimer ou à afficher)."""
    url, wifi = qr_targets(app)
    os.makedirs(QR_DIR, exist_ok=True)
    with open(os.path.join(QR_DIR, "raquette.png"), "wb") as f:
        f.write(qr.png(url))
    path = os.path.join(QR_DIR, "wifi.png")
    if wifi:
        with open(path, "wb") as f:
            f.write(qr.png(wifi))
    elif os.path.exists(path):
        os.remove(path)


def qr_page(app):
    url, wifi = qr_targets(app)
    nom = html.escape(app.cfg["reseau"]["wifi_nom"])
    card = lambda title, svg, sub: (f'<div class="card"><h2>{title}</h2>{svg}<p>{sub}</p></div>')
    cards = []
    if wifi:
        cards.append(card("1. Se connecter au Wi-Fi", qr.svg(wifi, scale=7),
                          f"Réseau <b>{nom}</b> — ouvre l'appareil photo et vise le code."))
    else:
        cards.append('<div class="card"><h2>1. Wi-Fi</h2><p>Renseigne le nom et le mot de passe du Wi-Fi '
                     'dans la page de réglages (section « Réseau ») pour avoir ce QR code.</p></div>')
    cards.append(card("2. Prendre une raquette", qr.svg(url, scale=7),
                      f"{html.escape(url)}<br>Accepte l'avertissement de certificat, puis « Prendre la raquette »."))
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>QR codes Jokari</title>
<style>
 body {{ margin:0; padding:16px; font-family:system-ui,sans-serif; background:#fff; color:#111; }}
 h1 {{ font-size:22px; margin:0 0 12px; }}
 .grid {{ display:flex; flex-wrap:wrap; gap:16px; }}
 .card {{ border:2px solid #111; border-radius:14px; padding:16px; flex:1 1 300px; max-width:420px; text-align:center; }}
 .card svg {{ width:100%; height:auto; max-width:360px; }}
 h2 {{ font-size:19px; margin:0 0 8px; }} p {{ font-size:14px; word-break:break-all; }}
 .no-print {{ margin-top:16px; font-size:14px; color:#555; }}
 @media print {{ .no-print {{ display:none; }} body {{ padding:0; }} }}
</style></head><body>
<h1>Sonic Jokari — jouer avec son téléphone</h1>
<div class="grid">{''.join(cards)}</div>
<p class="no-print">Imprime cette page (Cmd/Ctrl + P) ou utilise les fichiers <code>qr/wifi.png</code> et
<code>qr/raquette.png</code>. Si l'adresse IP de l'ordinateur change (autre box, autre réseau), les QR codes sont
refaits au lancement : réimprime-les. Pour une adresse qui ne bouge plus, réserve l'IP de l'ordinateur dans la box.</p>
</body></html>"""


def phone_sound(cfg, slot):
    """Réglages du son joué par le téléphone lui-même (sabre + « toc »)."""
    T, s = cfg["telephone"], cfg["sabre"]
    i = slot or 0
    return {"sabre": bool(T["sabre_sur_telephone"] and slot is not None),
            "freq": float(s["frequence"]) * 2 ** (i * float(s["ecart_joueurs"]) / 12 + int(T["transposition"])),
            "vol": float(T["volume_sabre"]), "bright": float(s["brillance"]), "buzz": float(s["grain"]),
            "idle": float(s["repos"]), "fmax": float(T["sensibilite_sabre"]),
            "toc": bool(T["son_impact"]), "toc_vol": float(T["volume_impact"])}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"   # connexion gardée ouverte : indispensable pour la raquette

        def log_message(self, *a):
            pass

        def _file(self, name):
            with open(os.path.join(HERE, "web", name), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _raquette(self):
            body = json.loads(self._body() or b"{}")
            pid = re.sub(r"[^\w-]", "", str(body.get("id", "")))[:40]
            if not pid:
                raise ValueError("identifiant manquant")
            r = app.phones.get(pid)
            if "nom" in body:
                r.name = re.sub(r"[^\w \-'’]", "", str(body.get("nom", "")))[:20].strip()
            samples = []
            for s in body.get("s", [])[:400]:
                t, x, y, z = (float(v) for v in s[:4])
                samples.append((t, x, y, z))
            r.feed(samples)
            b = body.get("b")
            if b in ("home", "plus"):
                r.button(b)
            elif b == "tchin":
                r.on_event(r, "tchin", time.monotonic())
            elif b == "adversaire":
                app.game.post("action", 0, "adversaire")
            st = app.game.snapshot()
            self._json({"joueur": None if r.slot is None else r.slot + 1, "vibre": r.take_vibration(),
                        "message": st["message"], "etat": st["etat"], "points": st["points"],
                        "serveur": st["serveur"], "receveur": st["receveur"], "mode": st["mode"],
                        "adversaires": st["adversaires"], "parfait": st["parfait"],
                        "combo": st["combo"], "force": st["force"], "son": phone_sound(app.cfg, r.slot),
                        "choc": r.take_choc(), "noms": st["noms"], "nom": r.name, "actif": r.enabled,
                        "d": st["distance"], "v": st["vitesse"], "dref": st["dref"], "frappeur": st["frappeur"],
                        "elastique": st["elastique"]})

        def _json(self, obj, code=200):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(n) if n else b""

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                self._file("index.html")
            elif url.path in ("/studio", "/studio.html"):
                self._file("studio.html")
            elif url.path in ("/raquette", "/raquette.html"):
                self._file("raquette.html")
            elif url.path == "/qr":
                save_qr_files(app)
                data = qr_page(app).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif url.path == "/api/config":
                self._json({"config": app.cfg, "schema": SCHEMA, "samples": list_samples(),
                            "presets": list_presets(), "sons": SOUND_KINDS,
                            "sorties": audio.outputs(), "sortie_actuelle": app.engine.out,
                            "familles": FAMILLES})
            elif url.path == "/api/state":
                st = app.game.snapshot()
                st["raquettes"] = app.mgr.listing()
                self._json(st)
            else:
                self._json({"erreur": "introuvable"}, 404)

        def do_POST(self):
            url = urlparse(self.path)
            try:
                if url.path == "/api/raquette":
                    self._raquette()
                elif url.path == "/api/config":
                    changes = json.loads(self._body() or b"{}")
                    with app.game.lock:
                        for path, val in changes.items():
                            set_path(app.cfg, path, val)
                        save_config(app.cfg)
                    app.sound.push_all()
                    app.game.players_key = None       # resynchronise les sabres au prochain tour
                    if "general.sortie_audio" in changes:  # nouvelle sortie : on relance le son dessus
                        threading.Thread(target=app.engine.restart, args=("changement de sortie",), daemon=True).start()
                    self._json({"ok": True})
                elif url.path == "/api/action":
                    body = json.loads(self._body() or b"{}")
                    act = body.get("action", "")
                    if act == "coup":
                        app.game.post("coup", int(body.get("joueur", 1)) - 1, float(body.get("force", 0.7)))
                    elif act == "raquette":          # activer / désactiver une raquette depuis la page web
                        app.mgr.set_enabled(str(body.get("id", "")), bool(body.get("actif", True)))
                    elif act == "preset_save":
                        name = re.sub(r"[^\w\- ]", "", body.get("nom", ""))[:40].strip()
                        if not name:
                            raise ValueError("nom de préréglage vide")
                        os.makedirs(PRESETS_DIR, exist_ok=True)
                        with open(os.path.join(PRESETS_DIR, name + ".json"), "w", encoding="utf-8") as f:
                            json.dump(app.cfg, f, indent=2, ensure_ascii=False)
                    elif act == "preset_load":
                        name = os.path.basename(body.get("nom", ""))
                        new = load_config(os.path.join(PRESETS_DIR, name + ".json"))
                        with app.game.lock:
                            for k in new:
                                app.cfg[k] = new[k]
                            save_config(app.cfg)
                        app.sound.push_all()
                    elif act.startswith("test_"):      # tests de sons depuis la page de réglages
                        app.game.post("test", 0, body)
                    else:
                        app.game.post("action", 0, act)
                    self._json({"ok": True})
                elif url.path == "/api/upload":
                    name = os.path.basename(parse_qs(url.query).get("nom", [""])[0])
                    name = re.sub(r"[^\w\-. ]", "_", name)
                    if not name.lower().endswith(SAMPLE_EXT):
                        raise ValueError("formats acceptés : wav, aif, aiff, flac")
                    if int(self.headers.get("Content-Length", 0)) > 30 * 1024 * 1024:
                        raise ValueError("fichier trop gros (30 Mo max)")
                    os.makedirs(SAMPLES_DIR, exist_ok=True)
                    with open(os.path.join(SAMPLES_DIR, name), "wb") as f:
                        f.write(self._body())
                    self._json({"ok": True, "samples": list_samples()})
                else:
                    self._json({"erreur": "introuvable"}, 404)
            except Exception as e:
                self._json({"ok": False, "erreur": str(e)}, 400)
    return Handler


def find_sclang():
    """Trouve sclang sur Linux/Pi, Mac et Windows (ou via la variable JOKARI_SCLANG)."""
    cands = [os.environ.get("JOKARI_SCLANG"), shutil.which("sclang")]
    if sys.platform == "darwin":
        cands += ["/Applications/SuperCollider.app/Contents/MacOS/sclang",
                  os.path.expanduser("~/Applications/SuperCollider.app/Contents/MacOS/sclang")]
    elif sys.platform == "win32":
        for root in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                     os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cands += sorted(glob.glob(os.path.join(root, "SuperCollider*", "sclang.exe")), reverse=True)
    return next((c for c in cands if c and os.path.isfile(c)), None)


def start_supercollider(out_dev="", in_dev=""):
    sclang = find_sclang()
    if not sclang:
        print("[son] sclang introuvable : installe SuperCollider (voir README) ou règle JOKARI_SCLANG")
        return None
    env = dict(os.environ)
    env["JOKARI_OUT"], env["JOKARI_IN"] = out_dev, in_dev
    cmd = [sclang, os.path.join(HERE, "sc", "jokari.scd")]
    if sys.platform.startswith("linux"):
        if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
            env["QT_QPA_PLATFORM"] = "offscreen"          # Pi sans écran
        env.setdefault("SC_JACK_DEFAULT_OUTPUTS", "system:playback_1,system:playback_2")
        if shutil.which("pw-jack") and not env.get("JOKARI_NO_PWJACK"):
            cmd = ["pw-jack"] + cmd
    print(f"[son] lancement de {sclang}" + (f" — sortie : {out_dev}" if out_dev else ""))
    return subprocess.Popen(cmd, env=env, cwd=os.path.join(HERE, "sc"))


class Engine:
    """Processus SuperCollider : choix de la sortie audio, relance si besoin, et (Mac) suivi de la
    sortie par défaut : brancher une enceinte Bluetooth bascule le son dessus en quelques secondes."""

    def __init__(self, cfg, sound):
        self.cfg, self.sound = cfg, sound
        self.proc, self.out = None, ""
        self.lock = threading.Lock()

    # --- serveur son (scsynth) : on s'assure qu'il ne reste jamais un ancien serveur bloqué ---
    @staticmethod
    def _scsynth(ppid=None):
        """PID des scsynth sur le port 57110 (optionnellement : enfants de ppid). Mac / Linux seulement."""
        if sys.platform == "win32":
            return []
        try:
            out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, timeout=3).stdout
        except Exception:
            return []
        pids = []
        for line in out.splitlines():
            parts = line.split(None, 2)
            if len(parts) == 3 and "scsynth" in parts[2] and "57110" in parts[2]:
                if ppid is None or int(parts[1]) == ppid:
                    pids.append(int(parts[0]))
        return pids

    @staticmethod
    def _port_busy():
        t = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            t.bind(("127.0.0.1", 57110))
            return False
        except OSError:
            return True
        finally:
            t.close()

    @staticmethod
    def _kill(pids):
        for pid in pids:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.kill(pid, sig)
                except OSError:
                    break
                for _ in range(10):
                    time.sleep(0.1)
                    try:
                        os.kill(pid, 0)
                    except OSError:
                        break
                else:
                    continue
                break

    def _clear_port(self):
        """Avant de démarrer : si un ancien serveur son occupe encore le port, on l'arrête."""
        if not self._port_busy():
            return
        osc.OscClient("127.0.0.1", 57110).send("/quit")
        for _ in range(15):
            time.sleep(0.1)
            if not self._port_busy():
                return
        orphans = self._scsynth(ppid=1)
        if orphans:
            print(f"[son] ancien serveur son bloqué (pid {', '.join(map(str, orphans))}) : arrêt")
            self._kill(orphans)
        if self._port_busy():
            print("[son] attention : le port 57110 est encore occupé (un autre SuperCollider est ouvert ?)")

    def _start(self):
        self._clear_port()
        out, inp, warn = audio.choose(self.cfg["general"]["sortie_audio"])
        self.out = out
        if warn:
            print("[son] attention :", warn)
        self.proc = start_supercollider(out, inp)

    def _stop(self):
        if self.proc:
            children = self._scsynth(ppid=self.proc.pid)        # le serveur son lancé par ce sclang
            osc.OscClient("127.0.0.1", 57110).send("/quit")    # arrêt normal du serveur son
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except Exception:
                self.proc.kill()
            # un serveur attaché à un périphérique qui a disparu (enceinte Bluetooth éteinte)
            # peut ne pas répondre : on le force
            time.sleep(0.3)
            self._kill([p for p in children if p in self._scsynth()])
        self.proc = None

    def start(self):
        with self.lock:
            self._start()
        if sys.platform == "darwin":
            threading.Thread(target=self._watch, daemon=True).start()

    def stop(self):
        with self.lock:
            self._stop()

    def restart(self, why, only_if_changed=False):
        with self.lock:
            if only_if_changed and audio.choose(self.cfg["general"]["sortie_audio"])[0] == self.out:
                return                                   # déjà relancé entre-temps sur la bonne sortie
            print(f"[son] relance de SuperCollider ({why})…")
            self.sound.ready = False
            self._stop()
            time.sleep(0.5)
            self._start()

    def check(self):
        """Relance SuperCollider s'il s'est arrêté tout seul."""
        if self.proc and self.proc.poll() is not None and not self.lock.locked():
            self.restart("il s'est arrêté")

    def _watch(self):
        while True:
            time.sleep(3)
            if not self.proc or self.lock.locked():      # une relance est déjà en cours
                continue
            out, _, _ = audio.choose(self.cfg["general"]["sortie_audio"])
            if out and out != self.out:
                self.restart(f"sortie audio : {out}", only_if_changed=True)


class App:
    pass


def main():
    ap = argparse.ArgumentParser(description="Sonic Jokari")
    ap.add_argument("--sim", action="store_true", help="ajoute 2 joueurs virtuels")
    ap.add_argument("--no-sc", action="store_true", help="ne pas lancer SuperCollider")
    ap.add_argument("--port", type=int, default=8080, help="port de la page web")
    ap.add_argument("--https-port", type=int, default=8443, help="port HTTPS (raquette téléphone)")
    ap.add_argument("--no-browser", action="store_true", help="ne pas ouvrir la page de réglages")
    args = ap.parse_args()

    app = App()
    app.cfg = load_config()
    if args.sim and not app.cfg["jeu"]["joueurs_virtuels"]:
        app.cfg["jeu"]["joueurs_virtuels"] = 2
    save_config(app.cfg)

    app.sound = Sound(app.cfg)
    holder = {}
    app.mgr = WiimoteManager(app.cfg, lambda w, k, v: holder["game"].on_wiimote(w, k, v))
    app.game = holder["game"] = Game(app.cfg, app.sound, app.mgr)
    app.phones = PhoneHub(app.cfg, app.mgr, lambda w, k, v: holder["game"].on_wiimote(w, k, v))
    if not app.mgr.available:
        print("[wiimote] aucun pilote Wiimote (installe evdev sur Linux, hidapi sur Mac/Windows) : "
              "téléphones et simulation seulement")

    threading.Thread(target=announce_to_hub, daemon=True).start()
    app.engine = Engine(app.cfg, app.sound)
    if not args.no_sc:
        app.engine.start()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ip = local_ip()
    name = app.cfg["reseau"]["adresse"].strip() or local_name()
    app.addr, app.ip, app.https_port = name or ip, ip, args.https_port
    print(f"[web] réglages : http://localhost:{args.port}  (ou http://{ip}:{args.port})")
    # HTTPS : les navigateurs ne donnent les capteurs de mouvement qu'aux pages sécurisées
    cert = ensure_cert(os.path.join(HERE, "certs"), ip, name)
    if cert:
        try:
            srv_tls = ThreadingHTTPServer(("0.0.0.0", args.https_port), make_handler(app))
            wrap_https(srv_tls, *cert)
            threading.Thread(target=srv_tls.serve_forever, daemon=True).start()
            print(f"[téléphone] raquette : https://{ip}:{args.https_port}/raquette  "
                  "(même Wi-Fi ; accepter l'avertissement de certificat)")
            print(f"[téléphone] QR codes à imprimer : http://localhost:{args.port}/qr  (et dossier qr/)")
            try:
                save_qr_files(app)
            except Exception as e:
                print("[téléphone] QR codes non enregistrés :", e)
        except OSError as e:
            print("[téléphone] HTTPS impossible :", e)
    else:
        print("[téléphone] openssl introuvable : pas de raquette téléphone (installe OpenSSL)")
    if not args.no_browser and sys.platform in ("darwin", "win32"):
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    # fermer la fenêtre du terminal (ou arrêter le service) arrête proprement le jeu et le son
    def stop(*_):
        raise KeyboardInterrupt
    for sig in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), stop)

    last = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            app.game.step(min(now - last, 0.05))
            last = now
            app.engine.check()
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        app.engine.stop()


if __name__ == "__main__":
    main()
