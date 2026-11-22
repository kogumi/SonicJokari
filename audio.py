"""Choix de la sortie audio (Mac).

- On peut choisir la sortie dans la page de réglages (haut-parleurs, enceinte Bluetooth…),
  ou laisser « sortie par défaut du Mac » : le jeu suit alors les changements de sortie.
- SuperCollider ne doit jamais ouvrir le micro d'une enceinte ou d'un casque Bluetooth :
  ça la ferait passer en mode « kit mains libres » (mono, 16 kHz). On lui donne donc un micro
  intégré (le jeu n'utilise pas d'entrée audio).

Sur Linux / Pi / Windows : rien à faire ici (la sortie se règle côté système / JACK).
"""
import json
import subprocess
import sys


def devices():
    """Liste des périphériques audio du Mac : nom, entrées, sorties, fréquence, Bluetooth, défauts."""
    if sys.platform != "darwin":
        return []
    try:
        out = subprocess.run(["system_profiler", "SPAudioDataType", "-json"],
                             capture_output=True, text=True, timeout=8).stdout
        items = json.loads(out)["SPAudioDataType"][0]["_items"]
    except Exception:
        return []
    res = []
    for d in items:
        res.append({
            "nom": d.get("_name", ""),
            "entrees": int(d.get("coreaudio_device_input", 0) or 0),
            "sorties": int(d.get("coreaudio_device_output", 0) or 0),
            "frequence": int(d.get("coreaudio_device_srate", 0) or 0),
            "bluetooth": "bluetooth" in str(d.get("coreaudio_device_transport", "")),
            "integre": "builtin" in str(d.get("coreaudio_device_transport", "")),
            "sortie_defaut": d.get("coreaudio_default_audio_output_device") == "spaudio_yes",
            "entree_defaut": d.get("coreaudio_default_audio_input_device") == "spaudio_yes",
        })
    return res


def outputs(devs=None):
    """Noms des sorties disponibles (sans doublon)."""
    names = []
    for d in devs if devs is not None else devices():
        if d["sorties"] and d["nom"] not in names:
            names.append(d["nom"])
    return names


def choose(wanted, devs=None):
    """(sortie, entrée, avertissement) à donner à SuperCollider.
    wanted = nom choisi dans les réglages, ou "" pour la sortie par défaut du Mac."""
    devs = devs if devs is not None else devices()
    if not devs:
        return "", "", ""
    outs = [d for d in devs if d["sorties"]]
    out = next((d for d in outs if d["nom"] == wanted), None) if wanted else None
    if out is None:
        out = next((d for d in outs if d["sortie_defaut"]), outs[0] if outs else None)
    ins = [d for d in devs if d["entrees"] and not d["bluetooth"]]
    inp = (next((d for d in ins if d["entree_defaut"]), None)
           or next((d for d in ins if d["integre"]), None)
           or (ins[0] if ins else None))
    warn = ""
    if out and out["bluetooth"] and 0 < out["frequence"] <= 24000:
        warn = (f"« {out['nom']} » est en mode kit mains libres (mono, {out['frequence'] // 1000} kHz) : "
                "une autre application utilise son micro. Dans Réglages Système → Son → Entrée, "
                "choisis le micro du Mac, puis éteins et rallume l'enceinte pour retrouver la stéréo.")
    return (out["nom"] if out else ""), (inp["nom"] if inp else ""), warn
