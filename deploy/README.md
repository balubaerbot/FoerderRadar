# deploy/ - Reverse Proxy + TLS fuer foerdora.cloud

Ziel: `https://foerdora.cloud` soll die FoerderRadar-App ausliefern.
Die App laeuft im Container und ist nur als **127.0.0.1:8100:8000** veroeffentlicht -
also ausschliesslich vom Host erreichbar. Der Proxy auf dem Host ist das
einzige, was nach aussen auf 80/443 lauscht.

## Voraussetzungen (einmalig auf dem Host)

1. **Firewall oeffnen** - Ports 80 und 443 muessen von aussen erreichbar sein:
   - hPanel: VPS -> Firewall -> Regel fuer TCP 80 und 443
   - auf dem Host: `ufw allow 80/tcp && ufw allow 443/tcp`
   - Pruefen: `ss -tlnp | grep -E ':(80|443)\b'`

2. **DNS** - nichts zu tun. `foerdora.cloud  A  168.231.110.175` ist gesetzt.
   (Ein `www`-Record existiert nicht; die www-Blöcke in den Configs sind
   daher standardmaessig auskommentiert.)

## Variante A: nginx + certbot (empfohlen)

Alle Pakete kommen aus den offiziellen Ubuntu-Quellen - kein Drittanbieter-Repo,
kein Fremdschluessel. `nginx.conf` ist die **Phase-1-Fassung** (nur Port 80) und
laedt fehlerfrei, bevor ein Zertifikat existiert; certbot ergaenzt TLS danach selbst.

```bash
apt install -y nginx certbot python3-certbot-nginx
cp deploy/nginx.conf /etc/nginx/sites-available/foerdora
ln -sf /etc/nginx/sites-available/foerdora /etc/nginx/sites-enabled/foerdora
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
certbot --nginx -d foerdora.cloud
```

Das `rm -f .../sites-enabled/default` ist wichtig: Ubuntus Default-Site belegt
sonst Port 80 und die eigene Site greift nicht.

## Variante B: Caddy (aktuell NICHT via apt installierbar)

**Bekanntes Problem (Stand 01.10.2026):** Caddys apt-Repo laesst sich nicht
verifizieren. Der Signing-Subkey des aktuellen Schluessels ist seit **2024-03-30
abgelaufen** (`[SA] [expired: 2024-03-30]`), Cloudsmith signiert das `InRelease`
aber weiterhin damit. `apt update` bricht deshalb mit:

```
The following signatures were invalid: EXPKEYSIG 531A6B20FA058A70 Caddy Web Server
```

Nachgeprueft: `531A6B20FA058A70` ist der **Subkey** des aktuellen Hauptschluessels
`155B6D79CA56EA34` - **kein** veralteter Alt-Schluessel. Ein Neu-Import des
Schluessels aendert daran nichts (getestet). Das ist serverseitig und auf dem
Host nicht reparierbar.

Ausweg, falls Caddy unbedingt gewuenscht: statisches Binary statt apt-Repo.
`Caddyfile` bleibt unveraendert gueltig.

```bash
curl -fsSL 'https://caddyserver.com/api/download?os=linux&arch=amd64' -o /usr/local/bin/caddy
chmod +x /usr/local/bin/caddy
caddy version
```

Danach eine systemd-Unit anlegen (Binary hat keine mitgeliefert).

## Waehrend der Entwicklung: Zugangsschutz

Der Endpunkt ist oeffentlich, das Formular aber noch nicht fertig. Damit keine
Fremden Testeintraege in die Datenbank schreiben, ist in beiden Configs ein
**Basic-Auth-Block vorbereitet** (auskommentiert).

Caddy:
```bash
caddy hash-password --plaintext 'DEIN-PASSWORT'
# Hash in /etc/caddy/Caddyfile eintragen, basic_auth-Block einkommentieren
systemctl reload caddy
```

nginx:
```bash
htpasswd -c /etc/nginx/.htpasswd balu
# auth_basic-Zeilen einkommentieren
nginx -t && systemctl reload nginx
```

**Go-Live:** den Block wieder auskommentieren, reload. Fertig.

## DEV-Phase: Tor zu (aktueller Zustand)

Solange entwickelt wird, zeigt `foerdora.cloud` **keinen** oeffentlichen Inhalt.
`nginx-dev.conf` liefert nur eine Platzhalterseite; die App wird nicht
durchgereicht (ihr Port ist ohnehin nur `127.0.0.1:8100`).

```bash
mkdir -p /var/www/foerdora-dev
cp deploy/dev-placeholder.html /var/www/foerdora-dev/index.html
cp deploy/nginx-dev.conf /etc/nginx/sites-available/foerdora
nginx -t && systemctl reload nginx
```

**Go-Live-Schalter** (wenn oeffentlich werden soll):

```bash
cp deploy/nginx.conf /etc/nginx/sites-available/foerdora
nginx -t && systemctl reload nginx
```

**App waehrend der Dev-Phase selbst testen** - nicht ueber die Domain, sondern
per SSH-Tunnel auf den Loopback-Port des Hosts:

```bash
ssh -L 8100:127.0.0.1:8100 hostinger-openclaw
# dann im Browser: http://localhost:8100
```

Zum Testen der App ggf. `FOERDER_ADMIN_TOKEN` als Bearer-Header mitschicken -
die Middleware ist Default-Deny (siehe `PUBLIC` in `app/main.py`).

## Wichtig: Proxy-Header in der App

Damit die App die echte Client-IP und `https` als Schema sieht (Rate-Limit pro
IP!), startet uvicorn mit:

```
--proxy-headers --forwarded-allow-ips=*
```

Das steht als `command:` in `docker-compose.yml` (nicht im Dockerfile - so
genuegt ein Recreate, kein Rebuild). `*` ist hier vertretbar, weil der Port
ausschliesslich an 127.0.0.1 gebunden ist - nur Host-Prozesse (der Proxy) koennen
ueberhaupt verbinden. Waere der Port oeffentlich, muesste man den Docker-Gateway
(172.18.0.1) explizit eintragen.

**Container neu erstellen** (vom Host, kein Rebuild noetig):

```bash
cd /docker/openclaw-jpva/data/projects/FoerderRadar
docker compose up -d foerderradar-api
```

## Verifikation

```bash
curl -I https://foerdora.cloud            # erwartet: HTTP/2 200
curl -sI http://foerdora.cloud | head -1  # erwartet: 301 -> https
```

TLS und Zertifikat:
```bash
echo | openssl s_client -connect foerdora.cloud:443 -servername foerdora.cloud 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```
