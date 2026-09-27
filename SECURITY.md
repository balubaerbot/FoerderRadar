# FoerderRadar — Sicherheits- & Datenschutzkonzept

**Grundsatz:** *Default-Deny.* Nur was muss, ist öffentlich erreichbar. Die
Trennung pseudonyme Daten ↔ Klartext-Kontaktdaten wird **technisch erzwungen**,
nicht nur per Konvention.

Stand: 2026-09-27 (Entwurf)

---

## Ist-Stand

| Prüfung | Ergebnis |
|---|---|
| API von außen erreichbar? | **Nein** — nur `127.0.0.1:8100` ✅ |
| DB veröffentlicht? | **Nein** — nur im Docker-Netz ✅ |
| Auth in der API? | **Keine** — 6 Endpunkte offen ⚠️ |
| DB-Rolle `foerderradar` | **Superuser**, kann `kontakt` lesen ⚠️ |

---

## 1. Netzwerk / Exposition

- **Öffentlich:** nur die Website + `POST /profile` (hinter Reverse-Proxy mit **TLS**).
- **Intern:** DB, `GET /profiles`, `POST/GET /match`, `/health`, Versand-Worker.
- FoerderRadar bleibt ein **eigenes Docker-Projekt** (nicht im `openclaw`-Stack).
- Der OpenClaw-Container erreicht die DB ueber `openclaw-jpva_default` — gewollt
  (Agent liest nur `profil_agent`) → macht die Rollen-Trennung (§3) unverzichtbar.

## 2. Authentifizierung / Autorisierung

- `POST /profile` — öffentlich, aber mit **Rate-Limit + Validierung + Bot-Schutz**.
- **Admin-Endpunkte** (`/profiles`, `/match`, …) — **Token** (SecretRef), nur intern.
- Jede Route explizit freigeben (Default-Deny).

## 3. Datenbank-Rollen (erzwungene Trennung)

Ziel: kein Dienst kann mehr, als er braucht.

| Rolle | darf | darf **NICHT** |
|---|---|---|
| `app_web` (öffentliche API) | `INSERT profil`, `INSERT kontakt` | `SELECT kontakt` |
| `app_agent` (Matching/Agent) | `SELECT profil_agent`, `INSERT/DELETE match` | `SELECT kontakt` |
| `app_worker` (Versand) | `SELECT kontakt`, `INSERT/SELECT versand`, `UPDATE match` | — |

> Folge: Der Agent kann Klartext **technisch nicht** lesen — auch wenn er es
> wollte. Erfordert getrennte Connections/Aufrufe fuer Schreib- und Lesepfad.

## 4. Transport & Speicherung

- **TLS** fuer Website ↔ API (Reverse-Proxy).
- **Backups verschluesseln** — sie enthalten Klartext-Kontaktdaten!
- Disk-at-rest pruefen.
- DB-Passwort als **SecretRef** (nicht im Klartext in `.env`).

## 5. DSGVO

- **Consent:** Checkbox + Text + Zeitstempel → `einwilligung_am`.
- **Loeschkonzept:** Job arbeitet `loeschdatum` ab (Art. 17).
- Auskunft/Berichtigung moeglich.
- Datenminimierung: pseudonym (`profil`) vs. Klartext (`kontakt`) getrennt.

## 6. Kunden-Konten

- **Empfehlung: kein Kunden-Login.** Kein Passwortspeicher = kleinere Angriffsflaeche.
- Ergebnis per **Mail** (+ optional personalisierter **Token-Link**, kein Konto).
- **Admin-Login** fuer den Betrieb — getrennt und stark abgesichert.

## 7. Umsetzungs-Checkliste

- [x] API-Auth + Default-Deny (Admin-Endpunkte) — Token via `FOERDER_ADMIN_TOKEN` (`.env`, gitignored)
- [ ] DB-Rollen-Trennung (`app_web` / `app_agent` / `app_worker`)
- [x] Rate-Limit auf `POST /profile` (5/Minute/IP) — Bot-Schutz (Honeypot/CAPTCHA) offen
- [ ] TLS + Reverse-Proxy
- [ ] Backups verschluesseln
- [x] Consent-Flow: `einwilligung` Pflichtfeld in `POST /profile` (Nachweis-Text noch offen)
- [ ] Loesch-Job fuer `loeschdatum`
