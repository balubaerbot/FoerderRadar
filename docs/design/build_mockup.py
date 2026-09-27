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
input,select{width:100%;padding:12px 14px;border:1.5px solid var(--line);border-radius:10px;
             font-size:15.5px;background:#fff;font-family:inherit}
input:focus,select:focus{outline:0;border-color:var(--p2)}
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
<a href="#">Wie es funktioniert</a><a href="#">Förderungen</a><a href="#">Kontakt</a>
<a class="btn btn-p" style="padding:11px 20px;font-size:15px" href="#">Jetzt starten</a>
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
      <a class="btn btn-p" href="#">Für Betriebe</a>
      <a class="btn btn-o" href="#">Für Privatpersonen</a>
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

# ---------------------------------------------------------------- Formular
formular = screen("Fördora — Angaben", HEAD + f"""
<main class="wrap" style="max-width:820px;padding-top:40px">
  <p class="small" style="margin-bottom:6px">Schritt 1 von 1 · dauert ca. 2 Minuten</p>
  <h1 style="font-size:32px">Ihre Angaben</h1>
  <p class="lead" style="font-size:16.5px;margin-bottom:26px">Je genauer, desto besser die Treffer.
     Pflichtfelder sind mit * markiert.</p>

  <div class="tabs"><div class="tab on">Betrieb</div><div class="tab">Privatperson</div></div>

  <div class="card">
    <div class="grid2">
      <div class="field"><label>Bundesland *</label>
        <select><option>Oberösterreich</option><option>Wien</option><option>Niederösterreich</option>
        <option>Salzburg</option><option>Tirol</option><option>Kärnten</option><option>Steiermark</option>
        <option>Vorarlberg</option><option>Burgenland</option></select></div>
      <div class="field"><label>Branche</label>
        <select><option>Handwerk / Gewerbe</option><option>IT / Digitalisierung</option>
        <option>Handel</option><option>Produktion</option><option>Sonstiges</option></select></div>
    </div>
    <div class="grid2">
      <div class="field"><label>Mitarbeiter</label>
        <select><option>1–4</option><option>5–9</option><option>10–49</option><option>50–249</option></select></div>
      <div class="field"><label>WKO-Mitglied?</label>
        <select><option>Ja</option><option>Nein</option></select></div>
    </div>

    <div class="field"><label>Ihr Vorhaben (Mehrfachauswahl)</label>
      <div class="chips">
        <span class="chip on">Digitalisierung</span><span class="chip on">Investition</span>
        <span class="chip">Schulung</span><span class="chip">Energieeffizienz</span>
        <span class="chip">Photovoltaik</span><span class="chip">Gründung</span>
      </div></div>

    <div class="field" style="margin-top:24px"><label>Projektkosten (ca., EUR)</label>
      <input value="25.000"></div>

    <hr style="border:0;border-top:1px solid var(--line);margin:24px 0">

    <h2 style="font-size:17px;margin-bottom:14px">Kontakt</h2>
    <div class="grid2">
      <div class="field"><label>Name *</label><input value="Max Mustermann"></div>
      <div class="field"><label>E-Mail *</label><input value="max@beispiel.at"></div>
    </div>
    <div class="field"><label>Telefon (optional, für SMS)</label><input value="+43 660 1234567"></div>

    <div class="consent">
      <input type="checkbox" checked>
      <div class="small" style="color:#134e4a">Ich willige ein, dass Fördora meine Angaben zur Prüfung
      möglicher Förderungen verarbeitet und mich per E-Mail/SMS kontaktiert. Diese Einwilligung kann ich
      jederzeit widerrufen.</div>
    </div>

    <button class="btn btn-p" style="width:100%;padding:16px;font-size:17px">Förderungen finden</button>
    <p class="small center" style="margin-top:14px">Keine Registrierung. Ihre Daten werden nur zur
      Prüfung verwendet.</p>
  </div>
  <div style="height:40px"></div>
</main>""" + FOOT)

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

for name, html in (("mockup-start", start), ("mockup-formular", formular), ("mockup-danke", danke)):
    (BASE / f"{name}.html").write_text(html, encoding="utf-8")
    print(f"{name}.html geschrieben")
