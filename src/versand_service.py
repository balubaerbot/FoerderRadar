"""FoerderRadar - Versand-Dienst (Phase 1: Entwurf + Dry-Run).

DATENSCHUTZ: Dieses Modul ist die EINZIGE Stelle, die Klartext-Kontaktdaten
liest (`kontakt`). Nach aussen gibt es sie NIE im Klartext aus - alle
Ausgaben/Logs werden maskiert. Der Agent ruft nur diesen Dienst auf und
sieht ausschliesslich maskierte Daten.

Ablauf:
  offene_kunden()      -> kunde_ids mit (neuen) Treffern, die kontaktiert werden duerfen
  treffer_fuer()       -> verifizierte Treffer (pseudonym)
  nachricht_bauen()    -> Betreff+Text aus pseudonymem Profil + Treffern (kein Klartext)
  entwurf_speichern()  -> Entwurf ablegen
  offene_entwuerfe()   -> Entwuerfe im Status 'entwurf'
  versenden()          -> sendet (oder Dry-Run) + protokolliert, markiert match 'gemeldet'
"""
import os
import re


def maskiere_email(adresse):
    """b****@gmail.com - damit der Agent nie die echte Adresse sieht."""
    if not adresse or "@" not in adresse:
        return "<keine>"
    name, dom = adresse.split("@", 1)
    return f"{name[0] if name else ''}****@{dom}"


def maskiere_telefon(nummer):
    """*****123 - nur die letzten 3 Ziffern."""
    if not nummer:
        return "<keine>"
    z = re.sub(r"\D", "", nummer)
    if len(z) <= 3:
        return "***"
    return "*" * (len(z) - 3) + z[-3:]


def _ziel_maskiert(kanal, kontakt):
    if kanal == "email":
        return maskiere_email(kontakt.get("email"))
    return maskiere_telefon(kontakt.get("telefon"))


# --------------------------------------------------------------------------
# Auswahl
# --------------------------------------------------------------------------
def offene_kunden(conn):
    """kunde_ids mit mind. einem Match 'identifiziert' UND gueltiger Einwilligung.

    Bedingungen: Einwilligung vorhanden, kein ueberschrittenes Loeschdatum,
    Kanal gesetzt.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT m.kunde_id
            FROM match m
            JOIN kontakt k ON k.kunde_id = m.kunde_id
            WHERE m.status = 'identifiziert'
              AND k.einwilligung_am IS NOT NULL
              AND (k.loeschdatum IS NULL OR k.loeschdatum > CURRENT_DATE)
              AND k.kanal IN ('email','sms')
            ORDER BY m.kunde_id
            """
        )
        return [r[0] for r in cur.fetchall()]


def treffer_fuer(conn, kunde_id):
    """Verifizierte Treffer (pseudonym - ohne Kontaktdaten)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT foerderung_id, kategorie, status FROM match
               WHERE kunde_id = %s AND status = 'identifiziert'
               ORDER BY CASE kategorie WHEN 'top' THEN 0 ELSE 1 END, foerderung_id""",
            (kunde_id,),
        )
        return [{"foerderung_id": r[0], "kategorie": r[1]} for r in cur.fetchall()]


def profil_pseudonym(conn, kunde_id):
    """Pseudonymes Profil (View profil_agent) - keine Kontaktdaten."""
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM profil_agent WHERE kunde_id = %s", (kunde_id,))
        cols = [c.name for c in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else None


def kontakt_holen(conn, kunde_id):
    """EINZIGE Stelle mit Klartext. Rueckgabe NUR intern verwenden, nie ausgeben."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, email, telefon, kanal FROM kontakt WHERE kunde_id = %s",
            (kunde_id,),
        )
        r = cur.fetchone()
    return {"name": r[0], "email": r[1], "telefon": r[2], "kanal": r[3]} if r else None


# --------------------------------------------------------------------------
# Text (Phase 1: Vorlage - Phase 2: LLM)
# --------------------------------------------------------------------------
def nachricht_bauen(profil, treffer, katalog):
    """Betreff + Text aus pseudonymem Profil + verifizierten Treffern. KEIN Klartext."""
    kat = {f["id"]: f for f in katalog["foerderungen"]}
    zeilen = []
    for t in treffer:
        f = kat.get(t["foerderung_id"])
        if not f:
            continue
        marker = "[sehr passend]" if t["kategorie"] == "top" else "[evtl. relevant]"
        zeilen.append(
            f"- {marker} {f['name']} ({f['stelle']})\n"
            f"  Leistung: {f['betrag']}\n"
            f"  Frist/Status: {f['frist']} (Status: {f['status']})\n"
            f"  Details: {f['quelle']}"
        )
    betreff = f"Ihre passenden Foerderungen ({len(zeilen)})"
    body = (
        "Guten Tag,\n\n"
        "auf Basis Ihrer Angaben koennen folgende Foerderungen fuer Sie relevant sein:\n\n"
        + "\n".join(zeilen)
        + "\n\nBitte pruefen Sie alle Angaben anhand der jeweiligen Quelle. "
        "Diese Zusammenstellung ist keine Rechts- oder Steuerberatung und ohne Gewaehr.\n\n"
        "Freundliche Gruesse\nIhr FoerderRadar-Team"
    )
    return betreff, body


# --------------------------------------------------------------------------
# Queue
# --------------------------------------------------------------------------
def entwurf_speichern(conn, kunde_id, betreff, body, kanal):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO versand (kunde_id, kanal, betreff, body, status)
               VALUES (%s, %s, %s, %s, 'entwurf') RETURNING id""",
            (kunde_id, kanal, betreff, body),
        )
        vid = cur.fetchone()[0]
    conn.commit()
    return vid


def hat_offenen_entwurf(conn, kunde_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM versand WHERE kunde_id = %s AND status IN ('entwurf','gesendet') LIMIT 1",
            (kunde_id,),
        )
        return cur.fetchone() is not None


def offene_entwuerfe(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, kunde_id, kanal, betreff, body FROM versand
               WHERE status = 'entwurf' ORDER BY id"""
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# Versand (Phase 3: echte Zustellung)
# --------------------------------------------------------------------------
def _senden_email(kontakt, betreff, body):
    raise NotImplementedError("Echter E-Mail-Versand kommt in Phase 3 (SMTP).")


def _senden_sms(kontakt, body):
    raise NotImplementedError("SMS-Versand kommt spaeter.")


def versenden(conn, versand_id, dry_run=True):
    """Sendet einen Entwurf (oder Dry-Run) und protokolliert.

    Rueckgabe enthaelt NUR maskierte Kontaktdaten.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT kunde_id, kanal, betreff, body, status FROM versand WHERE id = %s",
            (versand_id,),
        )
        row = cur.fetchone()
    if not row:
        return {"ok": False, "fehler": "Entwurf nicht gefunden"}
    kunde_id, kanal, betreff, body, status = row
    if status != "entwurf":
        return {"ok": False, "fehler": f"Status ist '{status}', nicht 'entwurf'"}

    kontakt = kontakt_holen(conn, kunde_id)
    if not kontakt:
        return {"ok": False, "fehler": "kein Kontakt vorhanden"}
    ziel = _ziel_maskiert(kanal, kontakt)

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "versand_id": versand_id,
            "kunde_id": str(kunde_id),
            "kanal": kanal,
            "ziel": ziel,
            "betreff": betreff,
            "body": body,
        }

    try:
        if kanal == "email":
            _senden_email(kontakt, betreff, body)
        else:
            _senden_sms(kontakt, body)
    except Exception as e:  # noqa: BLE001
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE versand SET status='fehler', fehler_text=%s WHERE id=%s",
                (str(e)[:300], versand_id),
            )
        conn.commit()
        return {"ok": False, "fehler": str(e)[:200], "ziel": ziel}

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET status='gesendet', gesendet_am=now() WHERE id=%s",
            (versand_id,),
        )
        cur.execute(
            """UPDATE match SET status='gemeldet', gemeldet_am=now()
               WHERE kunde_id=%s AND status='identifiziert'""",
            (kunde_id,),
        )
    conn.commit()
    return {"ok": True, "dry_run": False, "versand_id": versand_id, "ziel": ziel}
