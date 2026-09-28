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
import datetime
import os
import re
import subprocess
from email.message import EmailMessage

# Absender (Testphase: baluopenclaw@gmail.com; wird beim Livegang umgestellt).
ABSENDER = os.environ.get("FOERDER_FROM", "baluopenclaw@gmail.com")
HIMALAYA_ACCOUNT = os.environ.get("HIMALAYA_ACCOUNT", "gmail")


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
    """Legt einen Entwurf an - idempotent pro Kunde und atomar.

    Sperrt die Profil-Zeile (`FOR UPDATE`), damit zwei parallele Worker nicht
    gleichzeitig einen Entwurf anlegen. Existiert bereits einer (entwurf/sendet/
    gesendet), wird None zurueckgegeben und nichts eingefuegt.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM profil WHERE kunde_id = %s FOR UPDATE", (kunde_id,))
        if cur.fetchone() is None:
            conn.commit()
            return None
        cur.execute(
            "SELECT 1 FROM versand WHERE kunde_id = %s "
            "AND status IN ('entwurf','sendet','gesendet') LIMIT 1",
            (kunde_id,),
        )
        if cur.fetchone() is not None:
            conn.commit()
            return None
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
            "SELECT 1 FROM versand WHERE kunde_id = %s "
            "AND status IN ('entwurf','sendet','gesendet') LIMIT 1",
            (kunde_id,),
        )
        return cur.fetchone() is not None


def offener_entwurf(conn, kunde_id):
    """Letzter offener/abgeschlossener Versand zu einem Kunden (oder None)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, status, betreff, body FROM versand WHERE kunde_id = %s "
            "AND status IN ('entwurf','sendet','gesendet') ORDER BY id DESC LIMIT 1",
            (kunde_id,),
        )
        r = cur.fetchone()
    return {"id": r[0], "status": r[1], "betreff": r[2], "body": r[3]} if r else None


def entwurf_aktualisieren(conn, versand_id, betreff, body):
    """Ersetzt den Text eines noch offenen Entwurfs (nur Status 'entwurf').

    Noetig, weil sich Treffer aendern koennen (Katalog/Fristen), der gespeicherte
    Entwurfstext aber sonst veraltet bliebe. Bereits 'sendet'/'gesendet' werden
    NICHT angetastet.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET betreff=%s, body=%s, test_gesendet_am=NULL "
            "WHERE id=%s AND status='entwurf'",
            (betreff, body, versand_id),
        )
        geaendert = cur.rowcount
    conn.commit()
    return geaendert


def offene_entwuerfe(conn):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, kunde_id, kanal, betreff, body, test_gesendet_am FROM versand
               WHERE status = 'entwurf' ORDER BY id"""
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


# --------------------------------------------------------------------------
# Versand (Phase 3: echte Zustellung)
# --------------------------------------------------------------------------
def _senden_email(to_addr, betreff, body):
    """Echter Versand ueber die himalaya-CLI (nutzt deren Auth; kein Passwort hier)."""
    msg = EmailMessage()
    msg["From"] = ABSENDER
    msg["To"] = to_addr
    msg["Subject"] = betreff
    msg.set_content(body)

    cmd = ["himalaya", "--account", HIMALAYA_ACCOUNT, "message", "send", "--save", "sent"]
    p = subprocess.run(cmd, input=msg.as_string(), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"himalaya send fehlgeschlagen: {(p.stderr or p.stdout).strip()[:250]}")
    return True


def _senden_sms(kontakt, body):
    raise NotImplementedError("SMS-Versand kommt spaeter.")


# --------------------------------------------------------------------------
# Schutz vor veralteten/doppelten Sendungen
# --------------------------------------------------------------------------
def _redigiere(text, kontakt):
    """Entfernt Klartext-Kontaktdaten aus beliebigem Text (Logs/Fehlermeldungen).

    Fehlertexte der Mail-CLI koennen die Empfaengeradresse enthalten - solche
    Rohfehler duerfen NIE gespeichert oder ausgegeben werden.
    """
    if not text:
        return text
    s = str(text)
    if kontakt:
        for wert in (kontakt.get("email"), kontakt.get("telefon")):
            if wert:
                ersatz = maskiere_email(wert) if "@" in wert else maskiere_telefon(wert)
                s = s.replace(wert, ersatz)
    return s


def _status_setzen(conn, versand_id, status, fehler_text):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET status=%s, fehler_text=%s, sendet_seit=NULL WHERE id=%s",
            (status, fehler_text, versand_id),
        )
    conn.commit()


def sendet_zuruecksetzen(conn, minuten=15):
    """Watchdog: haengende 'sendet'-Zeilen nach `minuten` zurueck auf 'entwurf'.

    Stuerzt ein Lauf zwischen Claim und Senden ab (Prozess tot, DB-Timeout),
    bliebe die Zeile sonst fuer immer auf 'sendet' - offene_entwuerfe() zeigt sie
    nicht, entwurf_speichern() legt keinen neuen an, versenden() verweigert.
    Der Kunde waere dauerhaft blockiert. Rueckgabe: Anzahl zurueckgesetzter Zeilen.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET status='entwurf', sendet_seit=NULL, "
            "fehler_text='Watchdog: haengender Versand zurueckgesetzt' "
            "WHERE status='sendet' AND sendet_seit IS NOT NULL "
            "AND sendet_seit < now() - make_interval(mins => %s)",
            (minuten,),
        )
        n = cur.rowcount
    conn.commit()
    return n


def _kontakt_status(conn, kunde_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT einwilligung_am, loeschdatum, kanal FROM kontakt WHERE kunde_id = %s",
            (kunde_id,),
        )
        return cur.fetchone()


def _hat_offene_treffer(conn, kunde_id):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM match WHERE kunde_id = %s AND status = 'identifiziert' LIMIT 1",
            (kunde_id,),
        )
        return cur.fetchone() is not None


def _versandblocker(conn, kunde_id):
    """Prueft die Versandbedingungen ERNEUT unmittelbar vor dem Senden.

    Ein Entwurf kann veralten: Einwilligung widerrufen, Loeschfrist abgelaufen,
    Kanal entzogen oder keine offenen Treffer mehr. Rueckgabe: Grund (str) oder None.
    """
    info = _kontakt_status(conn, kunde_id)
    if not info:
        return "kein Kontakt vorhanden"
    einwilligung_am, loeschdatum, kanal = info
    if einwilligung_am is None:
        return "Einwilligung fehlt"
    if loeschdatum is not None and loeschdatum <= datetime.date.today():
        return "Loeschfrist abgelaufen"
    if kanal not in ("email", "sms"):
        return f"Kanal '{kanal}' nicht versendbar"
    if not _hat_offene_treffer(conn, kunde_id):
        return "keine offenen Treffer mehr (Entwurf veraltet)"
    return None


def versenden(conn, versand_id, dry_run=True, test_recipient=None):
    """Sendet einen Entwurf (oder Dry-Run) und protokolliert.

    test_recipient gesetzt -> echter Versand, aber an DIESE Adresse umgeleitet
    (Prototyp: eigenes Postfach). Der Entwurf bleibt danach OFFEN ('entwurf'),
    damit der spaetere echte Kundenversand moeglich ist.

    Schutz gegen Doppelversand: Der Entwurf wird atomar auf 'sendet' beansprucht
    (`UPDATE ... WHERE status='entwurf'`). Nur ein Aufruf gewinnt. Einwilligung,
    Loeschfrist, Kanal und offene Treffer werden unmittelbar vor dem Senden
    erneut geprueft. Fehlertexte werden von Kontaktdaten bereinigt.

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
    ziel = _ziel_maskiert(kanal, kontakt) if kontakt else "<keine>"

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
            "blocker": _versandblocker(conn, kunde_id),
        }

    # --- atomar beanspruchen: verhindert Doppelversand bei parallelen Laeufen ---
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET status='sendet', sendet_seit=now() "
            "WHERE id=%s AND status='entwurf' RETURNING id",
            (versand_id,),
        )
        claimed = cur.fetchone()
    conn.commit()
    if not claimed:
        return {"ok": False, "fehler": "Entwurf wird bereits bearbeitet/versendet", "ziel": ziel}

    # Ab hier liegt die Zeile auf 'sendet'. ALLES in try/except, damit eine
    # unerwartete Exception die Zeile NICHT dauerhaft blockiert (sonst kein neuer
    # Entwurf und kein Versand mehr moeglich - siehe sendet_zuruecksetzen).
    try:
        # --- Bedingungen unmittelbar vor dem Versand erneut pruefen ---
        blocker = _versandblocker(conn, kunde_id)
        if blocker:
            _status_setzen(conn, versand_id, "fehler", blocker)
            return {"ok": False, "fehler": blocker, "ziel": ziel}

        # Zieladresse bestimmen (Testphase: umleiten aufs Testpostfach)
        if test_recipient:
            to_addr = test_recipient
        elif kanal == "email":
            to_addr = kontakt.get("email")
        else:
            to_addr = kontakt.get("telefon")
        if not to_addr:
            _status_setzen(conn, versand_id, "entwurf", None)
            return {"ok": False, "fehler": f"keine Zieladresse fuer Kanal '{kanal}'", "ziel": ziel}

        if kanal == "email":
            _senden_email(to_addr, betreff, body)
        else:
            _senden_sms(kontakt, body)
    except Exception as e:  # noqa: BLE001
        meldung = _redigiere(str(e), kontakt)[:300]
        _status_setzen(conn, versand_id, "fehler", meldung)
        return {"ok": False, "fehler": meldung[:200], "ziel": ziel}

    ziel_tatsaechlich = maskiere_email(to_addr) if kanal == "email" else maskiere_telefon(to_addr)
    if test_recipient:
        # Testversand: Entwurf bleibt offen, damit der echte Kundenversand
        # spaeter moeglich ist (ein Test darf ihn NICHT dauerhaft blockieren).
        _status_setzen(
            conn, versand_id, "entwurf",
            f"TEST an {ziel_tatsaechlich} ({datetime.datetime.now():%Y-%m-%d %H:%M}) - Entwurf bleibt offen",
        )
        # Dedup: merken, dass GENAU dieser Text schon test-versendet wurde.
        # Aendert sich der Text spaeter (neue Treffer), setzt entwurf_aktualisieren
        # die Marke zurueck -> dann wird erneut test-versendet. So schickt ein
        # Cron-Lauf NICHT bei jeder Runde dieselbe Testmail.
        with conn.cursor() as cur:
            cur.execute("UPDATE versand SET test_gesendet_am=now() WHERE id=%s", (versand_id,))
        conn.commit()
        return {"ok": True, "dry_run": False, "test": True, "versand_id": versand_id,
                "ziel": ziel_tatsaechlich, "empfaenger_kunde": ziel}

    with conn.cursor() as cur:
        cur.execute(
            "UPDATE versand SET status='gesendet', gesendet_am=now(), fehler_text=NULL WHERE id=%s",
            (versand_id,),
        )
        cur.execute(
            """UPDATE match SET status='gemeldet', gemeldet_am=now()
               WHERE kunde_id=%s AND status='identifiziert'""",
            (kunde_id,),
        )
    conn.commit()
    return {"ok": True, "dry_run": False, "versand_id": versand_id, "ziel": ziel}
