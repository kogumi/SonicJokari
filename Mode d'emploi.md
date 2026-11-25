# Sonic Jokari — mode d'emploi

Un jeu de raquette **sans image** : on joue les yeux fermés (ou presque), guidé uniquement par le son.
On frappe une balle virtuelle, on l'entend partir au loin, revenir… et le joueur suivant doit la renvoyer au bon moment.

---

## 1. Lancer le jeu

### Sur Mac (sans VS Code)

1. Ouvre le dossier `jokari-sonore`.
2. **Double-clique sur `Lancer Jokari (Mac).command`.**
   - La première fois, si macOS refuse : clic droit sur le fichier → **Ouvrir** → **Ouvrir**.
3. Une fenêtre Terminal s'ouvre (elle affiche ce qui se passe), puis la **page de réglages** s'ouvre dans le navigateur.
4. Attends la ligne `[son] SuperCollider prêt` dans le Terminal : le son est prêt.
5. **Garde la fenêtre Terminal ouverte** pendant la partie.
6. **Pour arrêter : ferme la fenêtre Terminal** (ou tape Ctrl+C dedans). Le son s'arrête avec.

> Astuce : glisse `Lancer Jokari (Mac).command` dans le Dock (à droite) pour lancer le jeu en un clic.

### Sur Windows

Double-clique sur `Lancer Jokari (Windows).bat`. Même principe : garde la fenêtre ouverte, ferme-la pour arrêter.

### Sur Raspberry Pi (sans écran)

Une fois installé (voir `README.md`), le jeu **démarre tout seul** quand on branche le Pi.
On pilote tout depuis un téléphone : page de réglages sur `http://NOM-DU-PI.local:8080`.

### Avec VS Code (pour développer)

Menu Exécuter → « Jokari — manettes » ou « Jokari — simulation ».

### Choisir où sort le son (enceinte Bluetooth, haut-parleurs…)

- Par défaut, le jeu joue sur **la sortie son du Mac** et la **suit** : connecte ton enceinte Bluetooth et
  choisis-la dans le menu Son du Mac (icône haut-parleur en haut de l'écran) ; le son du jeu bascule dessus
  en quelques secondes.
- Ou choisis la sortie directement dans la page de réglages, section **« Son de l'ordinateur »**.
- Le son reste en **stéréo** : le jeu n'utilise jamais le micro d'une enceinte Bluetooth (sinon elle passe
  en mode « kit mains libres », mono et étouffé).

### Ce qu'il faut installer une seule fois (déjà fait sur le Mac de Simon)

- **Python 3** et **SuperCollider** (supercollider.github.io).
- Rien d'autre pour jouer avec des téléphones.

---

## 2. Connecter les joueurs

### Avec un téléphone (le plus simple)

1. Sur l'ordinateur, ouvre **http://localhost:8080/qr** (ou le lien « QR codes à imprimer » en haut de la page de réglages).
   Imprime la page. Le QR code de la raquette contient l'adresse IP de l'ordinateur : si elle change
   (autre box, autre réseau), les QR codes sont refaits au lancement, il suffit de les réimprimer.
   Pour qu'elle ne change plus, réserve l'adresse IP de l'ordinateur dans la box. Les images sont aussi dans `qr/`.
2. **QR code 1 — Wi-Fi** : le téléphone se connecte au bon réseau.
   (Pour l'avoir, renseigne le nom et le mot de passe du Wi-Fi dans la page de réglages, section « Réseau ».)
3. **QR code 2 — Raquette** : ouvre la page raquette.
   - Le navigateur prévient que la connexion n'est « pas privée » : c'est normal.
     iPhone : **Afficher les détails → visiter ce site web**. Android : **Paramètres avancés → Continuer**.
4. **Entre ton prénom** et appuie sur **Jouer** (iPhone : autorise l'accès aux mouvements).
5. En haut : ton prénom et **ton numéro de joueur**. Le petit personnage, c'est toi : il montre la partie en direct
   (la balle, l'élastique, « À toi ! » quand c'est ton tour). Monte le volume : ton sabre laser sort de ta main.
6. **Trois vues au choix** (boutons 💡 👤 🔢 en haut à droite), le score est toujours en haut :
   - 💡 **Lumière** : l'écran s'allume et pulse quand la balle revient vers toi, flashe quand tu frappes ;
   - 👤 **Personnage** : le petit bonhomme suit la partie en direct, avec les explications du jeu ;
   - 🔢 **Score** : juste les prénoms et les points, sans aucun effet.

Un seul onglet raquette par téléphone (sinon le téléphone compte pour deux joueurs).
Sur la page de réglages, la carte **👥 Joueurs** liste les raquettes : décoche un joueur pour le retirer de la partie
(un onglet en trop, quelqu'un qui fait une pause), recoche-le pour le faire revenir.

### Sans box : la borne Wi-Fi ESP32

Un ESP32-S3 (dossier `esp32-wifi/`) crée le réseau **SonicJokari** (mot de passe `sonicjokari`), sans internet :
1. Branche l'ESP32 (USB ou n'importe quel chargeur) : le réseau apparaît en quelques secondes.
2. Connecte **l'ordinateur** et **les téléphones** au Wi-Fi « SonicJokari ».
3. Lance le jeu : le QR code de la raquette prend tout seul la nouvelle adresse (192.168.4.x).
4. Pour le QR code Wi-Fi : dans les réglages, section Réseau, mets « SonicJokari » / « sonicjokari ».

Jusqu'à 10 appareils (limite de l'ESP32) : **au-delà, pour jouer jusqu'à 24, prends un vrai routeur Wi-Fi**
(même un vieux modèle) ou ta box. Pour changer le nom ou le mot de passe : `esp32-wifi/src/main.cpp`, puis
`~/.platformio/penv/bin/pio run -t upload` dans le dossier `esp32-wifi`.

### Avec des Wiimotes

- **Raspberry Pi / Linux** : lance `./raspberry-pi/appairer.sh` et appuie sur le bouton rouge SYNC de chaque manette.
- **Mac** : il faut une **DolphinBar Mayflash en mode 4** (le Bluetooth du Mac ne connecte plus les Wiimotes).
- La manette vibre et sa LED s'allume quand elle est reconnue.

---

## 3. Jouer

### Lancer une partie

- **On trinque** : on cogne doucement deux téléphones (ou deux Wiimotes) l'un contre l'autre. Chaque téléphone
  affiche « Tchin ! » quand il sent le choc.
- Seul contre l'ordinateur : appuie sur **🤖 Contre l'ordi**, la partie démarre.
- L'ordinateur annonce **qui commence**, avec ton prénom.

### Le déroulé

1. Le joueur qui sert fait **un grand geste** (comme un coup de raquette).
2. On entend la balle partir, s'éloigner, l'élastique se tendre (mode Jokari) ou la balle taper le mur (mode Pelote)…
3. …puis revenir vers le joueur suivant, de plus en plus vite. **Le son monte en tension** à son approche :
   un souffle pulsé qui accélère, puis la balle se double d'une **note à l'octave** juste avant le bon moment.
4. **Frappe quand tu l'entends arriver sur toi.** Trop tôt ou trop tard : tu perds le point.
5. Celui qui rate perd le point ; le gagnant sert. La voix dit « Point pour … »,
   et une petite **musique de victoire** salue le gagnant en fin de partie (« Bravo Simon, tu gagnes ! »).



### Ce qui change le jeu

| Ce que tu fais | Ce qui se passe |
|---|---|
| Frappe **douce** | La balle part lentement, pas très loin, revient doucement : facile pour l'adversaire. |
| Frappe **forte** | La balle file loin, l'élastique la ramène **plus tôt et plus fort** : dur à renvoyer. |
| Frappe **pile au bon moment** (quand la balle arrive sur toi) | **Frappe parfaite** : son « turbo », flash doré, vibration en rafale, la balle repart jusqu'à 2,5 fois plus vite. |
| Frappe **lente** | Le jeu **ralentit** : la balle flotte, revient tard, et le combo retombe un peu. |
| **Enchaîner les échanges** (combo) | La balle accélère, devient imprévisible (elle se promène dans l'espace), le son monte du grave vers l'aigu, de nouvelles couches de son s'ajoutent (sub, nappe, puis un **arpégiateur** qui accélère) et un « riser » monte jusqu'à l'arrivée de la balle. La voix annonce « combo 5, combo 10… ». Une faute remet le combo à zéro. |

L'écran du téléphone affiche aussi la **force** de ta dernière frappe (en % et en g) : pratique pour régler le jeu.

### Les boutons du téléphone

- **Nouvelle partie** : recommencer à zéro.
- **Mode** : passer de **Jokari** (élastique) à **Pelote** (mur au fond) et inversement.
- **🤖 Contre l'ordi** : jouer contre l'ordinateur (oui / non) ; seul, ça lance la partie.
- **Comment jouer ?** (en bas) : le rappel des règles.

### Style sonore

Dans la page de réglages (Son de l'ordinateur → Style sonore) : **Classique** (synthés intégrés) ou
**Dubstep — Lux Cache** : chaque joueur a son propre son de frappe (des samples qui tournent, avec une hauteur
qui varie) et la balle « wobble ».

**Mode musical** (bouton 🎵 de la page de réglages, désactivé par défaut) : un beat demi-tempo accompagne
la partie et s'étoffe avec le combo. Il marche avec les deux styles.

### Les deux modes

- **Jokari** : la balle est retenue par un élastique. Plus tu frappes fort, plus elle va loin et plus elle revient vite.
- **Pelote** : un mur au fond. Une balle trop faible n'atteint pas le mur : faute.

---

## 4. Régler le jeu

Tout se règle **en direct** sur la page de réglages (`http://localhost:8080`, ou depuis un téléphone).
Les réglages les plus utiles :

| Problème | Réglage (section) |
|---|---|
| Je suis toujours à 100 % de force | **Seuil de force max** ↑ (Téléphones) |
| Mes petits gestes ne frappent pas | **Seuil de frappe** ↓ (Téléphones) |
| Je frappe toujours trop tôt / trop tard | **Frappe parfaite : moment** et **Délai de grâce** (Physique) |
| C'est trop dur / trop facile | **Fenêtre de frappe**, **Vitesse max** (Physique) ; **Niveau** de l'adversaire virtuel (Jeu) |
| Le jeu va trop vite | **Raideur de l'élastique** ↓, **Longueur de l'élastique** ↑ (Physique) |
| Le combo monte trop vite | **Échanges pour le combo maximum** ↑ (Combo) |
| Le sabre du téléphone est trop fort / aigu | **Volume du sabre**, **Transposition** (Téléphones) |
| Je veux mes propres sons | Section « Son : … » → choisir un sample (wav/aif/flac), ou en envoyer un |

**🎛️ Studio son** (lien en haut de la page de réglages, ou `http://localhost:8080/studio`) : la **conduite** d'un échange
(une piste par son, de la frappe à l'arrivée), le **synthé de la balle** avec ses potentiomètres, et des **enveloppes de vol**
à dessiner (volume, filtre, hauteur, réverb entre la frappe et l'arrivée). Lance un vol de test ou la démo : la ligne dorée suit la balle.

On peut **enregistrer un préréglage** (en bas de la page) et le recharger plus tard.

Pour **régler le son à l'oreille** : en haut de la famille 🔊 Son, la boîte **🎧 Tester les sons** fait entendre
un vol de balle complet, le riser, la frappe de chaque joueur, la frappe parfaite ou la voix, à la force et au
niveau de combo choisis (sans compter de point). Et **▶ Démo de jeu** lance une vraie partie entre 2 à 4 joueurs
virtuels, en boucle, avec des frappes douces et fortes et des combos : règle les sons pendant qu'ils jouent
(les téléphones sont mis de côté pendant la démo). Le même bouton l'arrête.

---

## 5. En cas de problème

| Symptôme | Solution |
|---|---|
| Pas de son | Attends `SuperCollider prêt` dans le Terminal. Vérifie le volume, et la sortie choisie (réglages, « Son de l'ordinateur ») : la ligne `[son] lancement … — sortie : …` du Terminal dit où part le son. |
| L'enceinte Bluetooth sonne en mono, étouffée | Une autre application (visio, dictée…) utilise son micro. Réglages Système → Son → Entrée : choisis le micro du Mac, puis éteins et rallume l'enceinte. Le Terminal affiche aussi un avertissement. |
| La page raquette ne s'ouvre pas | Téléphone sur le **même Wi-Fi** (pas en 4G/5G). Essaie l'adresse avec l'IP affichée dans le Terminal. Sur Mac, Réglages Système → Réseau → Pare-feu : autoriser Python. |
| Android n'ouvre pas l'adresse en `.local` | Dans la page de réglages, section Réseau, mets l'adresse IP de l'ordinateur dans « Adresse de la machine », puis réimprime les QR codes. |
| « Aucun capteur de mouvement reçu » | Recharge la page et appuie sur « Prendre la raquette » ; iPhone : accepte l'accès aux mouvements. |
| Le téléphone ne fait pas de son | Monte le volume, désactive le mode silencieux, recharge la page. |
| L'iPhone ne vibre pas | Normal : Safari n'autorise pas le vibreur pour une page web. L'écran clignote à la place, et le « toc » sonne dans la main. |
| Un téléphone compte pour deux joueurs | Ferme les onglets en double sur le téléphone. |
| Le jeu ne démarre plus (« Address already in use ») | Une ancienne partie tourne encore : ferme son Terminal (ou redémarre l'ordinateur). |

---

## 6. Où sont les fichiers

```
Lancer Jokari (Mac).command     ← double-clic pour jouer (Mac)
Lancer Jokari (Windows).bat     ← double-clic pour jouer (Windows)
start.sh                        ← lancement Linux / Raspberry Pi
Mode d'emploi.md                ← ce document
README.md                       ← documentation technique (installation Pi, détails)
samples/   tes sons             presets/   tes préréglages
qr/        QR codes à imprimer  config.json   les réglages actuels
raspberry-pi/   fichiers d'installation du Pi
jokari.py, wiimote.py, phone.py, osc.py, qr.py, sc/, web/   le programme
```
