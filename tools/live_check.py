"""Live-Check der FoerderRadar-API (Absicherung + Rollen)."""
import json
import urllib.error
import urllib.request

import psycopg

env = {}
for line in open('.env'):
    if '=' in line and not line.strip().startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

TOK = env['FOERDER_ADMIN_TOKEN']
BASE = "http://foerderradar-api:8000"


def call(method, path, body=None, auth=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if body is not None:
        req.add_header('Content-Type', 'application/json')
    if auth:
        req.add_header('Authorization', 'Bearer ' + TOK)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


s, b = call('GET', '/health')
print('1) GET /health              ->', s, b)
print('   => DB-Rolle der API:', json.loads(b).get('role'))

print('2) GET /profiles ohne Auth  ->', call('GET', '/profiles')[0], '(erwartet 401)')
print('3) GET /profiles mit Auth   ->', call('GET', '/profiles', auth=True)[0], '(erwartet 200)')

s, b = call('POST', '/profile', {
    'typ': 'privat', 'region_grob': 'OOe-Steyr',
    'vorhaben': ['heizungstausch', 'sanierung'],
    'wohnsituation': 'eigenheim', 'heizung': 'gas',
    'email': 'final@example.com', 'kanal': 'email', 'einwilligung': True})
print('4) POST /profile            ->', s)
kid = json.loads(b).get('kunde_id') if s == 200 else None
if kid:
    print('5) POST /match/{id}         ->', call('POST', '/match/' + kid, auth=True)[0],
          '(erwartet 200, Bug gefixt)')

try:
    with psycopg.connect(env['DATABASE_URL'], connect_timeout=5) as c, c.cursor() as cur:
        cur.execute('SELECT count(*) FROM kontakt')
    print('6) Agent-Pfad SELECT kontakt -> ERLAUBT (Achtung!)')
except psycopg.errors.InsufficientPrivilege:
    print('6) Agent-Pfad SELECT kontakt -> VERWEIGERT (so soll das)')

with psycopg.connect(env['DATABASE_URL_ADMIN'], connect_timeout=5) as a, a.cursor() as ac:
    if kid:
        ac.execute('DELETE FROM profil WHERE kunde_id = %s', (kid,))
    a.commit()
print('   (Aufraeumen erledigt)')
