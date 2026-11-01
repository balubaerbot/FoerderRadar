"""Gemeinsame feste Textbausteine der Kunden-Mails (Treffer- und Keine-Treffer-Mail).

Bewusst ohne Abhaengigkeiten, damit ki_mapping und versand_service sie beide
nutzen koennen, ohne sich gegenseitig zu importieren.
"""

import re

# Einheitliche Grussformel aller Kunden-Mails (Markenschreibweise mit Umlaut).
GRUSS = "Freundliche Grüße\nIhr Fördora-Team"


def widerruf_hinweis(adresse):
    """Widerrufsweg im Mailtext (Checkliste: 'Widerrufsweg ... in jeder Mail').

    Gleicher Wortlaut in allen Mailtypen; die Erkennung in
    tools/process_withdrawals.py prueft Absenderadresse + Betreff 'Widerruf'.
    """
    return (
        "Möchten Sie keine weiteren Nachrichten erhalten, schreiben Sie von dieser "
        f"Adresse eine E-Mail mit dem Betreff „Widerruf“ an {adresse}. "
        "Ihre Daten werden dann gelöscht."
    )


def schluss(adresse):
    """Fester Mailschluss: Widerrufshinweis + Grussformel."""
    return widerruf_hinweis(adresse) + "\n\n" + GRUSS


_KA_MUSTER = re.compile(r"^\s*k\.\s?A\.?\s*", re.IGNORECASE)
_KA_ERSATZ = "Höhe nicht pauschal angegeben"


def betrag_anzeige(betrag):
    """Katalogwert 'betrag' fuer Kunden lesbar machen.

    Der Katalog nutzt 'k.A.' (keine Angabe) als Kurzform, z.B.
    'k.A. (einkommensabhaengige Transferzahlung); ...'. Im Mailtext wird daraus
    'Höhe nicht pauschal angegeben (einkommensabhaengige ...); ...'. Ein nacktes
    'k.A.' verweist auf den Details-Link. Alle anderen Werte bleiben unveraendert;
    der Katalog selbst wird nicht angefasst.
    """
    if not isinstance(betrag, str):
        return betrag
    m = _KA_MUSTER.match(betrag)
    if not m:
        return betrag
    rest = betrag[m.end():].strip()
    if not rest:
        return _KA_ERSATZ + ", siehe Details"
    return f"{_KA_ERSATZ} {rest}"
