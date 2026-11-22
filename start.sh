#!/bin/bash
# Lance le jeu (Linux, Raspberry Pi, Mac).
# Sur Linux sans PipeWire, démarre jackd sur la carte son choisie (JOKARI_ALSA, ex. hw:1).
cd "$(dirname "$0")"
if [ "$(uname)" = "Linux" ] && ! command -v pw-jack >/dev/null 2>&1; then
  export JOKARI_NO_PWJACK=1
  if ! pgrep -x jackd >/dev/null; then
    jackd -R -d alsa -d "${JOKARI_ALSA:-hw:0}" -r 48000 -p 256 -n 3 &
    sleep 2
  fi
fi
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" -u jokari.py "$@"
