#!/bin/bash
# Appaire les Wiimotes : appuie sur le bouton rouge SYNC (sous le clapet) ou 1+2 pendant le scan.
echo "Appuie sur SYNC (ou 1+2) sur chaque Wiimote…"
bluetoothctl --timeout 12 scan on >/dev/null
for mac in $(bluetoothctl devices | grep -i "RVL-CNT" | awk '{print $2}'); do
  echo "→ $mac"
  bluetoothctl trust "$mac" >/dev/null
  bluetoothctl connect "$mac"
done
