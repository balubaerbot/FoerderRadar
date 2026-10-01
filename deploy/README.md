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

## Variante A: Caddy (empfohlen)

Weniger Fehlerquellen: holt und erneuert Zertifikate selbst, ~15 Zeilen Config.

```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile
systemctl reload caddy
```

## Variante B: nginx + certbot

```bash
apt install nginx certbot python3-certbot-nginx
cp deploy/nginx.conf /etc/nginx/sites-available/foerdora
ln -s /etc/nginx/sites-available/foerdora /etc/nginx/sites-enabled/foerdora
nginx -t && systemctl reload nginx
certbot --nginx -d foerdora.cloud
```

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
