// Sonic Jokari — borne Wi-Fi autonome (ESP32-S3 en point d'accès).
// L'ordinateur du jeu et les téléphones s'y connectent : plus besoin d'une box.
// Adresse de l'ESP32 : 192.168.4.1 ; il distribue les adresses 192.168.4.x (DHCP).
//
// Adresse fixe pour le QR code : http://192.168.4.1 renvoie vers la page raquette du jeu,
// quelle que soit l'adresse reçue par l'ordinateur. Le jeu se signale à la borne toutes les
// 2 s (paquet UDP « SONICJOKARI » sur le port 4210).
//
// Réseau du jeu seulement : pas d'internet (la borne ne se connecte à rien).
//
// Téléphones rassurés : la borne est leur serveur DNS ; elle répond « 192.168.4.1 » à tout et
// répond elle-même aux tests de connexion
// d'Apple, Google, Microsoft et Firefox. Le téléphone garde alors le Wi-Fi au lieu de basculer
// en 4G/5G ou d'afficher « pas d'accès à internet » (sinon Chrome et Safari ne trouvent pas le jeu).
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <esp_wifi.h>

const char *NOM = "SonicJokari";        // nom du réseau
const char *MDP = "sonicjokari";        // mot de passe (8 caractères minimum)
const int CANAL = 6;
const int CLIENTS_MAX = 10;             // maximum de l'ESP32

WebServer web(80);
WiFiUDP udp, dns;                       // annonce du jeu, DNS des téléphones
const IPAddress ICI(192, 168, 4, 1);

IPAddress jeu;                          // adresse de l'ordinateur du jeu
uint32_t vuLe = 0;

bool jeuPresent() { return vuLe && millis() - vuLe < 15000; }

void attente() {                        // le jeu ne s'est pas encore signalé
  web.send(200, "text/html; charset=utf-8",
           "<meta name=viewport content='width=device-width'><meta http-equiv=refresh content=2>"
           "<body style='font:20px system-ui;background:#111418;color:#e8ecf1;text-align:center;padding-top:30vh'>"
           "Sonic Jokari<br><small>En attente du jeu sur l'ordinateur…</small></body>");
}

void renvoie(const String &url) {
  if (!jeuPresent()) return attente();
  web.sendHeader("Location", url);
  web.send(302, "text/plain", "");
}

void repondDns() {
  int n = dns.parsePacket();
  if (n < 12 || n > 512) { if (n) dns.flush(); return; }
  uint8_t q[512];
  dns.read(q, n);
  int i = 12;                           // tout nom -> 192.168.4.1
  while (i < n && q[i]) i += q[i] + 1;
  if (i + 5 > n) return;
  uint16_t type = q[i + 1] << 8 | q[i + 2];
  int fin = i + 5;
  uint8_t r[530];
  memcpy(r, q, fin);
  r[2] = 0x81; r[3] = 0x80;             // réponse, récursion disponible, pas d'erreur
  r[6] = 0; r[7] = (type == 1);         // une réponse pour A (IPv4), aucune pour le reste
  r[8] = r[9] = r[10] = r[11] = 0;
  int k = fin;
  if (type == 1) {
    const uint8_t a[] = {0xC0, 0x0C, 0, 1, 0, 1, 0, 0, 0, 30, 0, 4, 192, 168, 4, 1};
    memcpy(r + k, a, sizeof(a)); k += sizeof(a);
  }
  dns.beginPacket(dns.remoteIP(), dns.remotePort()); dns.write(r, k); dns.endPacket();
}

void setup() {
  Serial.begin(115200);
  // ordre de l'exemple officiel (WiFiExtender) : démarrer le point d'accès, le configurer, puis le créer
  WiFi.AP.begin();
  WiFi.AP.config(IPAddress(192, 168, 4, 1), IPAddress(192, 168, 4, 1), IPAddress(255, 255, 255, 0),
                 IPAddress(192, 168, 4, 2), ICI);   // la borne est le DNS des téléphones
  WiFi.AP.create(NOM, MDP, CANAL, 0, CLIENTS_MAX);
  if (!WiFi.AP.waitStatusBits(ESP_NETIF_STARTED_BIT, 2000)) Serial.println("[wifi] ERREUR : point d'acces non demarre");
  WiFi.setTxPower(WIFI_POWER_19_5dBm);  // pleine puissance (antenne externe)
  esp_wifi_set_ps(WIFI_PS_NONE);        // pas de mise en veille : moins de latence
  udp.begin(4210);
  dns.begin(53);
  // tests de connexion des téléphones (sans internet) : on répond « tout va bien »
  web.on("/hotspot-detect.html", [] { web.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"); });
  web.on("/library/test/success.html", [] { web.send(200, "text/html", "<HTML><HEAD><TITLE>Success</TITLE></HEAD><BODY>Success</BODY></HTML>"); });
  web.on("/generate_204", [] { web.send(204); });
  web.on("/gen_204", [] { web.send(204); });
  web.on("/connecttest.txt", [] { web.send(200, "text/plain", "Microsoft Connect Test"); });
  web.on("/ncsi.txt", [] { web.send(200, "text/plain", "Microsoft NCSI"); });
  web.on("/success.txt", [] { web.send(200, "text/plain", "success\n"); });
  web.on("/", [] { renvoie("https://" + jeu.toString() + ":8443/raquette"); });
  web.on("/reglages", [] { renvoie("http://" + jeu.toString() + ":8080/"); });
  web.onNotFound([] { renvoie("https://" + jeu.toString() + ":8443/raquette"); });
  web.begin();
}

void loop() {
  web.handleClient();
  repondDns();
  if (udp.parsePacket()) {
    char buf[16] = {0};
    udp.read(buf, sizeof(buf) - 1);
    if (!strncmp(buf, "SONICJOKARI", 11)) { jeu = udp.remoteIP(); vuLe = millis(); }
  }
  static uint32_t t = 0;
  if (millis() - t > 5000) {            // état toutes les 5 s sur le port série
    t = millis();
    Serial.printf("[wifi] emet « %s » canal %d - ", WiFi.softAPSSID().c_str(), WiFi.channel());
    Serial.printf("%s - %d appareil(s) - jeu : %s\n", WiFi.softAPIP().toString().c_str(),
                  WiFi.softAPgetStationNum(), jeuPresent() ? jeu.toString().c_str() : "absent");
  }
  delay(2);
}
