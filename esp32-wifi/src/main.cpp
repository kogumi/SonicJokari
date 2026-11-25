// Sonic Jokari — borne Wi-Fi autonome (ESP32-S3 en point d'accès).
// L'ordinateur du jeu et les téléphones s'y connectent : plus besoin d'une box.
// Adresse de l'ESP32 : 192.168.4.1 ; il distribue les adresses 192.168.4.x (DHCP).
#include <WiFi.h>
#include <esp_wifi.h>

const char *NOM = "SonicJokari";        // nom du réseau
const char *MDP = "sonicjokari";        // mot de passe (8 caractères minimum)
const int CANAL = 6;
const int CLIENTS_MAX = 10;             // maximum de l'ESP32

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(NOM, MDP, CANAL, false, CLIENTS_MAX);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);  // pleine puissance (antenne externe)
  esp_wifi_set_ps(WIFI_PS_NONE);        // pas de mise en veille : moins de latence
}

void loop() {
  static uint32_t t = 0;
  if (millis() - t > 5000) {            // état toutes les 5 s sur le port série
    t = millis();
    Serial.printf("[wifi] %s %s - %d appareil(s) connecte(s)\n", NOM, WiFi.softAPIP().toString().c_str(),
                  WiFi.softAPgetStationNum());
  }
  delay(50);
}
