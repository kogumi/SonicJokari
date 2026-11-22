# Sonic Jokari

> **Samples du style « Dubstep — Lux Cache »** : ils viennent d'une banque commerciale et ne sont pas dans le dépôt
> (`samples/kits/` est ignoré par git). Sans eux, le jeu reprend tout seul les sons synthétisés. Pour les retrouver,
> copie les fichiers listés dans `kits/lux_dubstep.json` depuis ta banque Lux Cache vers `samples/kits/lux_dubstep/`.

Jeu de raquette **sans image** : la balle virtuelle n'existe que par le son.
Deux modes : **Jokari** (la balle est retenue par un élastique, elle ralentit puis revient en accélérant)
et **Pelote** (la balle file vers un mur au fond, claque et revient).
De 1 à 4 joueurs (et plus), avec des **téléphones** comme raquettes ou des Wiimotes classiques, et un adversaire virtuel.
Pour lancer le jeu et jouer : voir **[Mode d'emploi.md](Mode%20d'emploi.md)**.

- **Python** (`jokari.py`) : manettes, logique de jeu, vibreurs, page web de réglages.
- **SuperCollider** (`sc/jokari.scd`) : tout le son (balle Doppler, sabres, samples, réverb).
- Le même code tourne sur **Raspberry Pi**, **Mac**, **Windows** et **Linux**, avec une simple sortie stéréo.

| Machine | Manettes | Voix du score |
|---|---|---|
| Raspberry Pi / Linux | Bluetooth intégré (pilote `evdev`) | espeak-ng |
| Windows 10/11 | Bluetooth intégré ou DolphinBar (pilote `hidapi`) | voix Windows |
| Mac | **DolphinBar Mayflash en mode 4** (pilote `hidapi`) | `say` |

Sur Mac, le Bluetooth natif ne connecte plus les Wiimotes depuis macOS Monterey. La DolphinBar (environ 25 €, en USB)
contourne le problème. Elle marche aussi sur Windows et évite les galères d'appairage.

## Déroulé d'une partie

1. **Trinquer** : deux joueurs entrechoquent leurs Wiimotes → « tchin » → la partie démarre.
2. **Service** : un petit souffle est joué côté serveur, et sa manette vibre. Il frappe (geste ample).
3. **Vol** : la balle s'éloigne (plus grave, plus sourde, plus réverbérée), puis
   - Jokari : « boing » de l'élastique au loin, et retour en accélérant ;
   - Pelote : claquement sur le mur, et retour.
4. **Retour** : le son monte (Doppler), se resserre et s'accélère : c'est le moment de frapper.
   Seul le joueur dont c'est le tour peut renvoyer, et seulement dans la fenêtre de frappe.
5. **Faute** : le son descend, la manette vibre longuement, puis le point et le score sont annoncés à voix haute.
6. Le premier à atteindre le nombre de points gagne. Pour rejouer, on trinque à nouveau.

À 1 joueur, on joue contre soi-même et le jeu compte la série.
Chaque manette a son propre bourdon façon « sabre laser » (une hauteur différente par joueur),
qui réagit en continu aux mouvements. Les joueurs sont répartis de gauche à droite en stéréo.

**Boutons Wiimote** : HOME = nouvelle partie, + / − = changer de mode (annoncé à voix haute).

## Installation sur le Raspberry Pi (Raspberry Pi OS Bookworm)

```bash
sudo apt update
sudo apt install supercollider python3-evdev espeak-ng bluez
sudo usermod -aG input,bluetooth,audio $USER
# Le dossier doit être dans ~/jokari-sonore
```

**Sortie son** : le Pi 4 a une prise jack, mais **le Pi 5 n'en a pas**. Sur un Pi 5, il faut une petite carte son USB.
Pour trouver le nom de ta carte : `aplay -l`. Si ce n'est pas `hw:0`, règle `JOKARI_ALSA=hw:1` (dans `raspberry-pi/jokari.service`).

**Bluetooth** : les Wiimotes ne s'appairent pas « proprement » avec BlueZ. Il faut autoriser les périphériques non liés :
```bash
sudo sed -i 's/^#\?ClassicBondedOnly=.*/ClassicBondedOnly=false/' /etc/bluetooth/input.conf
sudo systemctl restart bluetooth
```

**LEDs joueur** (optionnel) :
```bash
sudo cp raspberry-pi/99-jokari-wiimote.rules /etc/udev/rules.d/ && sudo udevadm control --reload
```

Redémarre le Pi (pour que les groupes soient pris en compte).

## Connecter les Wiimotes

```bash
./raspberry-pi/appairer.sh
```
Pendant le scan, appuie sur le bouton rouge **SYNC** (sous le clapet des piles) ou sur **1+2** de chaque manette.
La manette vibre et sa LED s'allume quand elle est reconnue comme joueur. Les numéros sont attribués dans l'ordre de connexion.
Le jeu détecte en continu les manettes qui arrivent et celles qui partent.

## Timing et frappe parfaite

La fenêtre pour renvoyer est large (4 m), et on peut encore frapper un court instant (0,25 s) après
l'arrivée de la balle. Le **timing compte** : la frappe parfaite est au moment où tu entends la balle arriver
sur toi (± 0,12 s). Plus tu en es proche, plus la balle repart vite, jusqu'à ×2,5. Une frappe parfaite a son
propre son, vibre plus fort, et l'écran du téléphone flashe en doré. Tout se règle dans la section Physique.

## L'élastique (mode Jokari)

La balle vole librement jusqu'à la longueur de l'élastique (5 m), puis l'élastique se tend et la ramène,
de plus en plus fort à mesure qu'il s'étire. Plus tu frappes fort, plus elle va loin, plus elle revient tôt
et vite. Le combo raidit l'élastique : le jeu s'accélère.

## Combo

Chaque renvoi enchaîné fait monter le combo (une frappe parfaite compte triple). Plus il monte :
la balle accélère, devient erratique (elle part plus ou moins loin, a des à-coups de vitesse, se balade
dans l'espace stéréo quand elle est loin), et le son s'enrichit de nouvelles couches (sub, supersaw, arpégiateur, turbine).
La voix annonce « combo 5 », « combo 10 »… Une faute remet le combo à zéro. Réglages : section « Combo ».

## Adversaire virtuel

Pour jouer seul contre l'ordinateur : bouton **🤖 Adversaire virtuel** sur la page raquette,
ou réglages « Adversaires virtuels » (0 à 3) et « Niveau » (0 = rate souvent, 1 = ne rate presque jamais) dans la section Jeu.
Ils prennent les numéros après les vrais joueurs, servent et renvoient tout seuls, et trinquent toujours avec toi.
Avec 2 adversaires virtuels et aucune manette, ils jouent entre eux : pratique pour régler le son à l'oreille.

## Jouer avec des téléphones (sans Wiimote)

Chaque téléphone peut servir de raquette, seul ou mélangé avec des Wiimotes. Ça marche pareil sur ordinateur et sur le Pi.

1. Le téléphone doit être sur le **même Wi-Fi** que l'ordinateur ou le Pi.
2. Ouvre l'adresse affichée au lancement : `https://IP-DE-LA-MACHINE:8443/raquette`
   (ou le lien « Prendre ce téléphone comme raquette » sur la page de réglages).
3. Le navigateur prévient que le certificat n'est pas reconnu : c'est normal (il est créé par le jeu, dans `certs/`).
   Choisis « Continuer vers le site » / « Afficher les détails → visiter ce site ».
4. Appuie sur **Prendre la raquette** (sur iPhone, autorise l'accès aux mouvements).
5. Le grand chiffre est ton numéro de joueur. Pour lancer la partie, tous les joueurs appuient sur **🥂 Tchin** en même temps.

- Mêmes gestes que la Wiimote : coup ample = frappe, le son « sabre » suit les mouvements du téléphone.
- **Le téléphone joue aussi du son** : ton sabre laser sort de ton téléphone (sans délai, il suit tes gestes),
  et un « toc » claque dans ta main à chaque frappe (plus aigu et plus fort quand tu frappes fort, avec un zap
  sur une frappe parfaite). Monte le volume du téléphone. Réglages : section « Téléphones (raquette) »
  (sabre sur le téléphone ou sur l'ordinateur, volumes, transposition).
- **Vibreur** : sur Android, le téléphone vibre comme la Wiimote (frappe, faute, service, victoire).
  Safari sur iPhone n'autorise pas le vibreur pour une page web : l'écran clignote à la place.
- Les seuils des téléphones se règlent à part (section « Téléphones (raquette) » de la page de réglages).
- Tiens le téléphone fermement (une dragonne ou une coque avec cordon est vivement conseillée).
- Le HTTPS est obligatoire : sans lui, les navigateurs ne donnent pas les capteurs de mouvement.
  Le certificat est créé avec `openssl` (présent sur Mac, Linux et Pi ; à installer sur Windows).

## Lancer

```bash
./start.sh            # normal
./start.sh --sim      # + 2 joueurs virtuels, pour tester sans manette
```
Puis, depuis un téléphone sur le même réseau : **http://IP-DU-PI:8080**

Démarrage automatique à l'allumage (le Pi fonctionne alors sans écran) :
```bash
mkdir -p ~/.config/systemd/user && cp raspberry-pi/jokari.service ~/.config/systemd/user/
systemctl --user enable --now jokari
sudo loginctl enable-linger $USER
```

## Installation sur ordinateur (Mac / Windows / Linux)

1. Installe **Python 3.10+** et **SuperCollider** (supercollider.github.io).
   Le jeu trouve SuperCollider tout seul, sinon indique le chemin de `sclang` dans la variable `JOKARI_SCLANG`.
2. Dans le dossier du jeu : `python3 -m venv .venv` puis `.venv/bin/pip install -r requirements.txt`
   (Windows : `.venv\Scripts\pip install -r requirements.txt`).
3. Manettes :
   - **DolphinBar** : branche-la et mets-la en **mode 4** (bouton MODE). Appuie sur SYNC sur la barre, puis sur la Wiimote.
   - **Windows sans DolphinBar** : Paramètres → Bluetooth → Ajouter un appareil, en appuyant sur le bouton SYNC de la Wiimote.
     Si on te demande un code PIN, laisse-le vide et valide.
4. Double-clique sur `Lancer Jokari (Mac).command` (Mac) ou `Lancer Jokari (Windows).bat` (Windows), ou lance `./start.sh` (Linux). La page de réglages s'ouvre toute seule.

Sur Windows, si les manettes sont reconnues mais que la frappe ne réagit pas, c'est que l'écriture vers la manette ne passe pas.
Le jeu essaie alors automatiquement une seconde méthode, et le signale dans la console.

## Avec VS Code

Ouvre le dossier `jokari-sonore` dans VS Code et installe l'extension Python (VS Code la propose).
- **Terminal → Exécuter la tâche → « Installer les dépendances »** : crée l'environnement `.venv`.
- Onglet **Exécuter et déboguer** (▶), trois lancements possibles :
  - *Jokari — manettes* : le jeu normal ;
  - *Jokari — simulation* : 2 joueurs virtuels, à jouer depuis la page web ;
  - *Jokari — simulation sans lancer SuperCollider* : pour lancer SuperCollider à part (tâche « Lancer SuperCollider seul »)
    et voir sa console en direct.
- La console affiche les connexions des manettes (`[wiimote]`) et l'état du son (`[son]`).
- Ça marche aussi avec VS Code en connexion SSH sur le Pi (extension Remote-SSH).

## Page web de réglages

Tous les changements s'appliquent immédiatement et sont enregistrés dans `config.json`.
- **Jeu** : mode, points pour gagner, joueurs virtuels, trinquer pour lancer, annonce vocale.
- **Manettes** : seuils de frappe et de choc, durées de vibration.
- **Physique** : vitesse, fenêtre de frappe, distance de l'élastique ou du mur, rebond, frottement.
- **Son de la balle** : fréquence, FM, saturation, moteur, filtres proche/lointain, réverb, Doppler, climax.
- **Sabres** : fréquence, écart entre joueurs, brillance, grésillement.
- **Sons ponctuels** (impact, mur, élastique, faute, point, service, victoire, trinque) :
  choix d'un **sample** (ou du synthé intégré), **hauteur**, **hauteur aléatoire**, hauteur selon la force,
  volume, **volume aléatoire**, **filtre aléatoire**, réverb, avec un bouton ▶ Écouter.
- **Préréglages** : enregistre ou recharge un jeu de réglages complet (par exemple « atelier enfants » ou « concert »).
- **Samples** : envoie des .wav depuis le téléphone (ils vont dans `samples/`).
  Trois samples d'exemple sont fournis : `bois_toc.wav`, `mur_beton.wav`, `tchin_verre.wav`.
- **Simulation** : boutons « Frapper J1/J2… » et « Trinquer » pour tester sans manette.

## Réglages à faire en premier, avec de vraies manettes

- `seuil_coup` : s'il y a des frappes fantômes, monte-le ; si les coups doux ne passent pas, baisse-le.
- `seuil_choc` : si trinquer ne marche pas, baisse-le. Si la partie démarre toute seule, monte-le
  (il faut de toute façon deux chocs presque simultanés sur deux manettes différentes).
- `fenetre` (fenêtre de frappe) et `vitesse_max` : ce sont eux qui règlent la difficulté.

## Structure

```
jokari.py        jeu, physique, OSC, serveur web
wiimote.py       lecture des Wiimotes (evdev ou hidapi), coups, chocs, vibreur, LEDs
phone.py         téléphone comme raquette (même détection de gestes), certificat HTTPS
web/raquette.html  page raquette du téléphone (port 8443, HTTPS)
Lancer Jokari (Mac).command / Lancer Jokari (Windows).bat / start.sh   lancement Mac / Windows / Linux-Pi
raspberry-pi/     service systemd, appairage Bluetooth, règle udev des LEDs
qr.py            QR codes sans dépendance (page /qr, dossier qr/)
Mode d'emploi.md mode d'emploi pour lancer le jeu et jouer
.vscode/         lancements et tâches pour VS Code
audio.py         choix de la sortie audio (Mac)
osc.py           OSC minimal sans dépendance
sc/jokari.scd    moteur son SuperCollider
web/index.html   page de réglages
samples/         tes sons (wav/aif/flac)
presets/         préréglages enregistrés
```

Messages OSC vers SuperCollider (port 57120) : `/ball`, `/motion`, `/saber`, `/play`, `/load`, `/set`, `/voice`.
Tu peux donc refaire le son ailleurs (Max, Pd…) en écoutant ces mêmes messages.
