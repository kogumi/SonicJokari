// Sonic Jokari — borne Wi-Fi autonome (ESP32-S3 en point d'accès).
// L'ordinateur du jeu et les téléphones s'y connectent : plus besoin d'une box.
// Adresse de l'ESP32 : 192.168.4.1 ; il distribue les adresses 192.168.4.x (DHCP).
//
// Adresse fixe pour le QR code : http://192.168.4.1 renvoie vers la page raquette du jeu,
// quelle que soit l'adresse reçue par l'ordinateur. Le jeu se signale à la borne toutes les
// 2 s (paquet UDP « SONICJOKARI » sur le port 4210).
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>
#include <esp_wifi.h>

const char *NOM = "SonicJokari";        // nom du réseau
const char *MDP = "sonicjokari";        // mot de passe (8 caractères minimum)
const int CANAL = 6;
const int CLIENTS_MAX = 10;             // maximum de l'ESP32

WebServer web(80);
WiFiUDP udp;
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

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(NOM, MDP, CANAL, false, CLIENTS_MAX);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);  // pleine puissance (antenne externe)
  esp_wifi_set_ps(WIFI_PS_NONE);        // pas de mise en veille : moins de latence
  udp.begin(4210);
  web.on("/", [] { renvoie("https://" + jeu.toString() + ":8443/raquette"); });
  web.on("/reglages", [] { renvoie("http://" + jeu.toString() + ":8080/"); });
  web.onNotFound([] { renvoie("https://" + jeu.toString() + ":8443/raquette"); });
  web.begin();
}

void loop() {
  web.handleClient();
  if (udp.parsePacket()) {
    char buf[16] = {0};
    udp.read(buf, sizeof(buf) - 1);
    if (!strncmp(buf, "SONICJOKARI", 11)) { jeu = udp.remoteIP(); vuLe = millis(); }
  }
  static uint32_t t = 0;
  if (millis() - t > 5000) {            // état toutes les 5 s sur le port série
    t = millis();
    Serial.printf("[wifi] %s %s - %d appareil(s) - jeu : %s\n", NOM, WiFi.softAPIP().toString().c_str(),
                  WiFi.softAPgetStationNum(), jeuPresent() ? jeu.toString().c_str() : "absent");
  }
  delay(2);
}
