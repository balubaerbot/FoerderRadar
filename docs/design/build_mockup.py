#!/usr/bin/env python3
"""Erzeugt die Design-Mockups (Start / Formular / Danke) als HTML."""
import pathlib

BASE = pathlib.Path(__file__).resolve().parent

CSS = """
:root{--p:#0f766e;--p2:#14b8a6;--p3:#ecfdf5;--ink:#0f172a;--mut:#5b6475;
      --bg:#f8fafc;--card:#fff;--line:#e2e8f0;--warn:#b45309}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;align-items:center;justify-content:space-between;
       padding:18px 40px;background:#fff;border-bottom:1px solid var(--line)}
.logo{display:flex;align-items:center;gap:10px;font-weight:750;font-size:20px;letter-spacing:-.02em}
.mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,var(--p),var(--p2));
      display:grid;place-items:center}
nav{display:flex;gap:26px;align-items:center}
nav a{color:var(--mut);text-decoration:none;font-size:14.5px}
.wrap{max-width:1120px;margin:0 auto;padding:0 40px}
.btn{display:inline-block;border:0;border-radius:12px;padding:14px 24px;font-size:16px;
     font-weight:650;cursor:pointer;text-decoration:none}
.btn-p{background:var(--p);color:#fff}
.btn-o{background:#fff;color:var(--p);border:1.5px solid var(--p)}
h1{font-size:44px;line-height:1.15;letter-spacing:-.025em;margin:0 0 16px}
h2{font-size:26px;margin:0 0 10px;letter-spacing:-.01em}
.lead{font-size:19px;color:var(--mut);margin:0 0 28px;max-width:620px}
.small{font-size:13.5px;color:var(--mut)}
.hero{padding:76px 0 56px}
.cta{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:18px}
.trust{display:flex;gap:26px;flex-wrap:wrap;margin-top:8px}
.trust span{font-size:14px;color:var(--mut)}
.trust b{color:var(--p)}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:16px 0 64px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:26px}
.step-n{width:34px;height:34px;border-radius:50%;background:var(--p3);color:var(--p);
        display:grid;place-items:center;font-weight:750;margin-bottom:14px}
footer{background:#fff;border-top:1px solid var(--line);padding:22px 40px;color:var(--mut);font-size:14px}
footer a{color:var(--mut);text-decoration:none;margin-right:18px}
label{display:block;font-size:14px;font-weight:600;margin:0 0 6px}
input,select,textarea{width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;
             font-size:15.5px;background:#fff;font-family:inherit}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--p2)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.field{margin-bottom:18px}
.tabs{display:flex;gap:10px;margin-bottom:24px}
.tab{flex:1;text-align:center;padding:14px;border:1.5px solid var(--line);border-radius:12px;
     font-weight:650;cursor:pointer;background:#fff;color:var(--mut)}
.tab.on{border-color:var(--p);background:var(--p3);color:var(--p)}
.chips{display:flex;gap:10px;flex-wrap:wrap}
.chip{border:1.5px solid var(--line);border-radius:999px;padding:9px 16px;font-size:14.5px;background:#fff}
.chip.on{border-color:var(--p);background:var(--p3);color:var(--p);font-weight:600}
.consent{display:flex;gap:12px;align-items:flex-start;background:var(--p3);
         border:1px solid #a7f3d0;border-radius:12px;padding:16px;margin:22px 0}
.consent input{width:20px;height:20px;flex:0 0 auto;margin-top:2px;accent-color:var(--p)}
.note{background:#fffbeb;border:1px solid #fde68a;color:var(--warn);
      border-radius:12px;padding:14px 16px;font-size:14px}
.tick{width:76px;height:76px;border-radius:50%;background:var(--p3);display:grid;place-items:center;margin:0 auto 22px}
.center{text-align:center}
.eyebrow{display:inline-flex;align-items:center;gap:8px;background:var(--p3);color:var(--p);
  border:1px solid #a7f3d0;border-radius:999px;padding:7px 15px;font-size:13.5px;font-weight:650;margin-bottom:20px}
.sec-title{font-size:30px;letter-spacing:-.02em;margin:58px 0 6px}
.sec-sub{color:var(--mut);margin:0 0 26px;font-size:16.5px;max-width:640px}
.usp{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.usp .card{display:flex;gap:15px;align-items:flex-start}
.ico{width:42px;height:42px;border-radius:12px;background:var(--p3);display:grid;place-items:center;flex:0 0 auto}
.aibox{background:#0f172a;border-radius:18px;padding:34px 36px;margin:22px 0 70px;display:grid;
  grid-template-columns:1.15fr .85fr;gap:34px;align-items:center}
.aibox h2{color:#fff;font-size:25px;letter-spacing:-.015em}
.aibox p{color:#94a3b8;margin:10px 0 0;font-size:15.5px}
.aibox .row{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}
.tag{border:1px solid #334155;border-radius:999px;padding:7px 14px;font-size:13px;color:#cbd5e1}
.tag b{color:#5eead4;font-weight:650}
.flow{display:flex;flex-direction:column;gap:10px}
.flow div{background:#1e293b;border-radius:11px;padding:12px 16px;font-size:14px;color:#e2e8f0}
.flow span{color:#5eead4;font-weight:700;margin-right:8px}
"""

LOGO = ('<div class="logo"><span class="mark">'
        '<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" '
        'stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/>'
        '<circle cx="12" cy="12" r="3.4" fill="#fff" stroke="none"/></svg></span>Fördora</div>')

HEAD = f"""<header>{LOGO}<nav>
<a href="mockup-start.html">Wie es funktioniert</a><a href="mockup-standbein.html">Förderungen</a><a href="#">Kontakt</a>
<a class="btn btn-p" style="padding:11px 20px;font-size:15px" href="mockup-formular-betrieb.html">Jetzt starten</a>
</nav></header>"""

FOOT = ('<footer><a href="#">Impressum</a><a href="#">Datenschutz</a><a href="#">Kontakt</a>'
        '<span style="float:right">© 2026 Fördora</span></footer>')


def screen(titel, body):
    return (f'<!doctype html><meta charset="utf-8"><title>{titel}</title>'
            f'<style>{CSS}</style>{body}')


# ---------------------------------------------------------------- Startseite
start = screen("Fördora — Startseite", HEAD + f"""
<main class="wrap">
  <section class="hero">
    <div class="eyebrow">✦ KI-gestützt · nur amtliche Quellen</div>
    <h1>Finden Sie heraus, welche<br>Förderungen Ihnen zustehen.</h1>
    <p class="lead">Fördora gleicht Ihr Profil automatisch mit allen Förderprogrammen
       für Österreich ab – und meldet sich, sobald eine Frist naht.</p>
    <div class="cta">
      <a class="btn btn-p" href="mockup-formular-betrieb.html">Für Betriebe</a>
      <a class="btn btn-o" href="mockup-formular-privat.html">Für Privatpersonen</a>
    </div>
    <div class="trust">
      <span><b>✓</b> Kostenlos &amp; unverbindlich</span>
      <span><b>✓</b> Nur amtliche Quellen</span>
      <span><b>✓</b> Ohne Registrierung</span>
    </div>
  </section>
  <section class="steps">
    <div class="card"><div class="step-n">1</div><h2 style="font-size:19px">Angaben machen</h2>
      <p class="small">In 2 Minuten: ein paar Eckdaten zu Ihrem Vorhaben. Kein Papierkram.</p></div>
    <div class="card"><div class="step-n">2</div><h2 style="font-size:19px">Automatisch abgleichen</h2>
      <p class="small">Wir prüfen Ihren Fall gegen alle aktuellen Programme – belegt aus den Originalquellen.</p></div>
    <div class="card"><div class="step-n">3</div><h2 style="font-size:19px">Treffer erhalten</h2>
      <p class="small">Sie bekommen die passenden Förderungen per E-Mail – und einen Hinweis, wenn eine Frist läuft.</p></div>
  </section>

  <h2 class="sec-title">Das macht Fördora anders</h2>
  <p class="sec-sub">Andere Seiten sind Kataloge zum Selbst-Durchsuchen.
     Fördora arbeitet für Sie – automatisch und nachvollziehbar.</p>
  <section class="usp">
    <div class="card"><div class="ico">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"><path d="M22 6 12 13 2 6"/>
        <rect x="2" y="4" width="20" height="16" rx="2"/></svg></div>
      <div><h2 style="font-size:19px">Push statt Suchen</h2>
      <p class="small">Wir warten nicht, bis Sie suchen. Fördora meldet passende Treffer aktiv –
      und erinnert, bevor eine Frist abläuft.</p></div></div>

    <div class="card"><div class="ico">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></div>
      <div><h2 style="font-size:19px">Nachweisbar, keine Blackbox</h2>
      <p class="small">Jede Zusage kommt aus einer belegten Regel, nicht aus einer KI-Vermutung.
      Wir zeigen, welche Bedingung erfüllt ist.</p></div></div>

    <div class="card"><div class="ico">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
      <div><h2 style="font-size:19px">Datenschutz ohne Konto</h2>
      <p class="small">Keine Registrierung, kein Passwort. Kontaktdaten bleiben getrennt
      von der Auswertung – EU-Hosting.</p></div></div>

    <div class="card"><div class="ico">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5V6a2 2 0 0 1 2-2h12v16H6a2 2 0 0 0-2 2z"/>
        <path d="M8 8h8M8 12h6"/></svg></div>
      <div><h2 style="font-size:19px">Nur geprüfte Quellen</h2>
      <p class="small">Jede Förderung stammt aus amtlichen Originalquellen und ist verlinkt.
      Keine Quelle, keine Aufnahme.</p></div></div>
  </section>

  <section class="aibox">
    <div>
      <h2>Intelligenz, die nur beim Verstehen hilft.</h2>
      <p>Unsere KI liest Förderrichtlinien, versteht Ihr Vorhaben in normaler Sprache und
         formuliert die Treffer verständlich. Ob eine Förderung wirklich passt, entscheidet
         jedoch eine nachvollziehbare Regel – nicht die KI. So bleibt jede Zusage überprüfbar.</p>
      <div class="row">
        <div class="tag"><b>KI</b> versteht Ihre Angaben</div>
        <div class="tag"><b>Code</b> prüft die Bedingungen</div>
        <div class="tag">Jede Quelle <b>verlinkt</b></div>
      </div>
    </div>
    <div class="flow">
      <div><span>1</span>KI versteht, was Sie vorhaben</div>
      <div><span>2</span>Regeln prüfen jede Förderung</div>
      <div><span>3</span>Sie erhalten Treffer – mit Quelle</div>
    </div>
  </section>
</main>""" + FOOT)

# ---------------------------------------------------------------- Formular-Bausteine
# Kapselung: kleine, benannte Bausteine -> kein kopiertes Feld-Markup mehr.
BUNDESLAENDER = ("Oberösterreich", "Wien", "Niederösterreich", "Salzburg", "Tirol",
                 "Kärnten", "Steiermark", "Vorarlberg", "Burgenland")


def optionen(werte):
    return "".join(f"<option>{w}</option>" for w in werte)


def feld(label, inner, pflicht=False):
    return f'<div class="field"><label>{label}{" *" if pflicht else ""}</label>{inner}</div>'


def auswahl(label, werte, pflicht=False):
    return feld(label, f"<select>{optionen(werte)}</select>", pflicht)


def zeile(*felder):
    return '<div class="grid2">' + "".join(felder) + "</div>"


def chips_feld(label, eintraege):
    spans = "".join(f'<span class="chip{" on" if an else ""}">{text}</span>'
                    for text, an in eintraege)
    return feld(label, f'<div class="chips">{spans}</div>')


def anliegen(text):
    return ('<div class="field" style="margin-top:22px">'
            '<label>Beschreiben Sie kurz Ihr Anliegen '
            '<span style="color:var(--mut);font-weight:400">(optional)</span></label>'
            f'<textarea rows="4" style="resize:vertical">{text}</textarea>'
            '<p class="small" style="margin:7px 0 0">In eigenen Worten – die KI erkennt daraus '
            'Standbein und Themen. Die Prüfung selbst machen weiterhin die Regeln.</p></div>')


_KONTAKT = (
    '<hr style="border:0;border-top:1px solid var(--line);margin:24px 0">'
    '<h2 style="font-size:17px;margin-bottom:14px">Kontakt</h2>'
    + zeile(feld("Name", '<input value="Max Mustermann">', True),
            feld("E-Mail", '<input value="max@beispiel.at">', True))
    + feld("Telefon (optional, für SMS)", '<input value="+43 660 1234567">')
    + '<div class="consent"><input type="checkbox" checked>'
      '<div class="small" style="color:#134e4a">Ich willige ein, dass Fördora meine Angaben '
      'zur Prüfung möglicher Förderungen verarbeitet und mich per E-Mail/SMS kontaktiert. '
      'Diese Einwilligung kann ich jederzeit widerrufen.</div></div>'
    + '<a class="btn btn-p" href="mockup-danke.html" style="display:block;text-align:center;'
      'text-decoration:none;width:100%;padding:16px;font-size:17px">Förderungen finden</a>'
    + '<p class="small center" style="margin-top:14px">Keine Registrierung. Ihre Daten werden '
      'nur zur Prüfung verwendet.</p>'
)


def formular_seite(*bloecke):
    """Eine eigenstaendige Formularseite aus Feldbloecken zusammensetzen."""
    return screen("Fördora — Angaben", HEAD + (
        '<main class="wrap" style="max-width:820px;padding-top:40px">'
        '<p class="small" style="margin-bottom:6px">Schritt 1 von 1 · dauert ca. 2 Minuten</p>'
        '<h1 style="font-size:32px">Ihre Angaben</h1>'
        '<p class="lead" style="font-size:16.5px;margin-bottom:26px">Je genauer, desto besser '
        'die Treffer. Pflichtfelder sind mit * markiert.</p>'
        '<div class="card">' + "".join(bloecke) + _KONTAKT + '</div>'
        '<div style="height:40px"></div></main>') + FOOT)


# ---------------------------------------------------------------- Formulare je Standbein
formular_betrieb = formular_seite(
    zeile(auswahl("Bundesland", BUNDESLAENDER, True),
          auswahl("Branche", ("Handwerk / Gewerbe", "IT / Digitalisierung", "Handel",
                              "Produktion", "Sonstiges"))),
    zeile(auswahl("Mitarbeiter", ("1–4", "5–9", "10–49", "50–249")),
          auswahl("WKO-Mitglied?", ("Ja", "Nein"))),
    chips_feld("Ihr Vorhaben (Mehrfachauswahl)",
               (("Digitalisierung", True), ("Investition", True), ("Schulung", False),
                ("Energieeffizienz", False), ("Photovoltaik", False), ("Gründung", False))),
    anliegen("Wir wollen unsere Fertigung digitalisieren – die Energiekosten in der Werkstatt "
             "sind stark gestiegen."),
    zeile(feld("Projektkosten (ca., EUR)", '<input value="25.000">')),
)

formular_privat = formular_seite(
    zeile(auswahl("Bundesland", BUNDESLAENDER, True),
          auswahl("Wohnsituation", ("Eigentum", "Miete", "Gemeindewohnung", "bei Angehörigen"))),
    zeile(auswahl("Haushaltsgröße", ("1 Person", "2 Personen", "3 Personen", "4 Personen",
                                     "5+ Personen")),
          auswahl("Haushaltseinkommen (netto/Monat)", ("unter 1.500 €", "1.500–2.500 €",
                                                       "2.500–4.000 €", "über 4.000 €",
                                                       "keine Angabe"))),
    chips_feld("Ihr Vorhaben (Mehrfachauswahl)",
               (("Sanierung", True), ("Heizungstausch", True), ("Fenstertausch", False),
                ("Photovoltaik", False), ("E-Auto", False), ("Energieberatung", False))),
    anliegen("Ich möchte mein Haus sanieren – die Heizkosten sind stark gestiegen."),
    zeile(feld("Geschätzte Kosten (ca., EUR)", '<input value="12.000">')),
)

formular_sozial = formular_seite(
    zeile(auswahl("Bundesland", BUNDESLAENDER, True),
          auswahl("Lebenssituation", ("Pflege eines Angehörigen", "Kinderbetreuung",
                                      "Arbeitssuchend", "Pension",
                                      "Behinderung / Beeinträchtigung", "Alleinerziehend"))),
    zeile(auswahl("Haushaltsgröße", ("1 Person", "2 Personen", "3 Personen", "4 Personen",
                                     "5+ Personen")),
          auswahl("Haushaltseinkommen (netto/Monat)", ("unter 1.500 €", "1.500–2.500 €",
                                                       "2.500–4.000 €", "über 4.000 €",
                                                       "keine Angabe"))),
    chips_feld("Wobei brauchen Sie Unterstützung? (Mehrfachauswahl)",
               (("Heizkostenzuschuss", True), ("Pflegegeld", True), ("Kinderbetreuung", False),
                ("Wohnbeihilfe", False), ("Ausbildung", False), ("Barrierefreiheit", False))),
    anliegen("Ich pflege meine Mutter, die Heizkosten sind kaum leistbar."),
)


# ---------------------------------------------------------------- Danke
danke = screen("Fördora — Danke", HEAD + """
<main class="wrap" style="max-width:640px;padding-top:64px">
  <div class="card center" style="padding:44px 34px">
    <div class="tick">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#0f766e"
           stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 6 9 17l-5-5"/></svg>
    </div>
    <h1 style="font-size:30px">Danke, Max!</h1>
    <p class="lead" style="margin:0 auto 22px;font-size:16.5px">Wir prüfen Ihre Angaben jetzt gegen
      alle aktuellen Förderprogramme für Österreich.</p>
    <div style="background:var(--p3);border:1px solid #a7f3d0;border-radius:12px;
                padding:16px;text-align:left;margin-bottom:22px">
      <p class="small" style="margin:0;color:#134e4a"><b>Ihre Treffer kommen per E-Mail an</b><br>
      m****@beispiel.at</p>
    </div>
    <p class="small" style="text-align:left"><b>Wie es weitergeht:</b></p>
    <ul class="small" style="text-align:left;line-height:1.9;margin:6px 0 20px;padding-left:20px">
      <li>Wir gleichen Ihr Profil mit dem Katalog ab</li>
      <li>Sie erhalten die passenden Förderungen mit Betrag, Frist und Link</li>
      <li>Läuft eine Frist ab, melden wir uns rechtzeitig</li>
    </ul>
    <div class="note" style="text-align:left">Diese Zusammenstellung ersetzt keine Förder-,
      Rechts- oder Steuerberatung.</div>
  </div>
</main>""" + FOOT)

# ------------------------------------------------- Entwurf: 3. Standbein "Sozial"
# Zeigt die vorgeschlagene thema-Achse: die drei Standbeine sind nur Tueren,
# datenseitig ist "Sozial" = zielgruppe=privat + thema=sozial. Ein Eintrag kann
# mehrere Themen tragen (mehrwertige Liste) -> deshalb sind es Badges, keine Spalte.
EXTRA_CSS = """
.badge{display:inline-block;border:1px solid #a7f3d0;background:var(--p3);color:var(--p);
  border-radius:999px;padding:3px 11px;font-size:12.5px;font-weight:650;margin-left:6px}
.badge.neu{border-color:#fcd34d;background:#fffbeb;color:var(--warn)}
.door{display:flex;gap:15px;align-items:flex-start}
.door .ico{width:46px;height:46px;border-radius:13px;font-size:19px;display:grid;place-items:center;
  background:var(--p3);color:var(--p);font-weight:700}
.card.hl{border-color:var(--p);box-shadow:0 8px 26px rgba(15,118,110,.12)}
.filters{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 22px}
"""
standbein = screen("Fördora — Standbeine & Thema-Achse", HEAD + f"<style>{EXTRA_CSS}</style>" + """
<main class="wrap">
  <section class="hero" style="padding-bottom:40px">
    <div class="eyebrow">✦ KI-gestützt · nur amtliche Quellen</div>
    <h1>Förderungen und Unterstützung,<br>die zu Ihnen passen.</h1>
    <p class="lead">Fördora gleicht Ihr Profil automatisch mit Förderungen und
       Sozialangeboten für Österreich ab – und meldet sich, sobald eine Frist naht.</p>
    <div class="cta">
      <a class="btn btn-p" href="mockup-formular-betrieb.html">Für Betriebe</a>
      <a class="btn btn-o" href="mockup-formular-privat.html">Für Privatpersonen</a>
      <a class="btn btn-o" href="mockup-formular-sozial.html">Sozial &amp; Alltag</a>
    </div>
    <div class="trust">
      <span><b>✓</b> Kostenlos &amp; unverbindlich</span>
      <span><b>✓</b> Nur amtliche Quellen</span>
      <span><b>✓</b> Ohne Registrierung</span>
    </div>
  </section>

  <h2 class="sec-title" style="margin-top:34px">Drei Standbeine, ein Radar</h2>
  <p class="sec-sub">Jeder Bereich funktioniert nach demselben Prinzip – nur die
     passenden Angebote unterscheiden sich.</p>
  <section class="steps" style="padding-bottom:34px">
    <div class="card"><div class="door"><div class="ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18M5 21V7l7-4 7 4v14"/><path d="M9 21v-6h6v6"/></svg></div><div>
      <h2 style="font-size:19px">Betrieb &amp; Förderung</h2>
      <p class="small">Digitalisierung, Investitionen, Energie, Gründung –
      Wirtschaftsförderung für Unternehmen.</p></div></div></div>
    <div class="card"><div class="door"><div class="ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l9-8 9 8"/><path d="M5 10v11h14V10"/></svg></div><div>
      <h2 style="font-size:19px">Privat &amp; Zuhause</h2>
      <p class="small">Sanieren, Heizen, Photovoltaik, Handwerkerbonus –
      Förderungen rund um Wohnen.</p></div></div></div>
    <div class="card hl"><div class="door"><div class="ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#0f766e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3"/><path d="M2 21v-1a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v1"/><path d="M17 8h4M19 6v4"/></svg></div><div>
      <h2 style="font-size:19px">Sozial &amp; Alltag <span class="badge neu">neu</span></h2>
      <p class="small">Heizkostenzuschuss, Wohnbeihilfe, Pflege &amp;
      Barrierefreiheit – Unterstützung für Menschen.</p></div></div></div>
  </section>

  <h2 class="sec-title" style="margin-top:8px">Filtern nach Thema</h2>
  <p class="sec-sub">Ein Angebot kann mehreren Themen zugeordnet sein
     (z.&nbsp;B. die Wohnbeihilfe ist <i>sozial</i> und <i>wohnen</i>).</p>
  <div class="filters">
    <span class="chip">wirtschaft</span><span class="chip on">sozial</span>
    <span class="chip">energie</span><span class="chip">wohnen</span>
    <span class="chip">bildung</span>
  </div>

  <div class="card" style="margin-bottom:34px"><div style="display:flex;justify-content:space-between;
       align-items:flex-start;gap:16px;flex-wrap:wrap">
    <div><h2 style="font-size:19px;margin:0">Heizkostenzuschuss Oberösterreich</h2>
      <p class="small" style="margin:6px 0 0">Zuschuss zu den Heizkosten für Haushalte
      mit geringem Einkommen.</p></div>
    <div><span class="badge">sozial</span><span class="badge">energie</span></div>
  </div>
  <p class="small" style="margin:14px 0 0">
    <b style="color:var(--p)">bis 300 €</b> &nbsp;·&nbsp; Frist 31.10.2026
    &nbsp;·&nbsp; Quelle: land-oberoesterreich.gv.at &nbsp;✓ amtlich</p></div>

  <section class="aibox">
    <div>
      <h2>Intelligenz, die nur beim Verstehen hilft.</h2>
      <p>Unsere KI liest Förderrichtlinien und versteht Ihr Vorhaben in normaler Sprache –
         sie erkennt, welches Standbein und welche Themen passen. Ob eine Förderung
         wirklich zutrifft, entscheidet jedoch eine nachvollziehbare Regel, nicht die KI.
         So bleibt jede Zusage überprüfbar.</p>
      <div class="row">
        <div class="tag"><b>KI</b> versteht Ihre Angaben</div>
        <div class="tag"><b>Code</b> prüft die Bedingungen</div>
        <div class="tag">Jede Quelle <b>verlinkt</b></div>
      </div>
      <p class="small" style="margin:16px 0 0;color:#94a3b8;font-size:13.5px">
        Beispiel: „Ich pflege meine Mutter, die Heizkosten sind kaum leistbar“
        → erkannt als <b style="color:#5eead4;font-weight:650">privat</b> ·
        <b style="color:#5eead4;font-weight:650">sozial</b> ·
        <b style="color:#5eead4;font-weight:650">energie</b></p>
    </div>
    <div class="flow">
      <div><span>1</span>KI versteht, was Sie vorhaben</div>
      <div><span>2</span>Regeln prüfen jede Förderung</div>
      <div><span>3</span>Sie erhalten Treffer – mit Quelle</div>
    </div>
  </section>
</main>""" + FOOT)

for name, html in (('mockup-start', start),
                   ('mockup-formular-betrieb', formular_betrieb),
                   ('mockup-formular-privat', formular_privat),
                   ('mockup-formular-sozial', formular_sozial),
                   ('mockup-danke', danke), ('mockup-standbein', standbein)):
    (BASE / f'{name}.html').write_text(html, encoding='utf-8')
    print(f'{name}.html geschrieben')
