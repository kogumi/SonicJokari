#!/bin/bash
# Mac : double-clic pour lancer le jeu. Garde cette fenêtre ouverte pendant la partie ;
# pour arrêter : ferme la fenêtre (ou Ctrl+C).
cd "$(dirname "$0")" && exec ./start.sh "$@"
