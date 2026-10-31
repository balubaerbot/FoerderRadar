# Operator runbook: verified customer deletion request

Status: **DRAFT — not activated.** This runbook describes how an operator executes one
requested profile deletion with `tools/delete_profile_on_request.py`. It has been
rehearsed only against a throwaway local PostgreSQL cluster (see "Rehearsal record").
It does not authorize any production deletion, migration, role change, or intake
activation. Production use requires a separate, explicit approval.

## 1. What the workflow does

- `tools/delete_profile_on_request.py <kunde_id>` calls
  `public.delete_profile_on_request(uuid)` once, in one transaction.
- The function (defined in `db/init.sql` and repeated in
  `db/migrations/20261019_request_deletion.sql`) runs as `SECURITY DEFINER` and:
  - deletes the `profil` row; linked `kontakt`, `match` and `versand` rows are removed
    through `ON DELETE CASCADE`;
  - ignores the retention date (`loeschdatum`), unlike the retention purge;
  - inserts one row into `profile_deletion_audit` containing only `kunde_id`,
    `requested_at`, `deleted_at`. No contact data is written to the audit table.
- Exit codes of the tool:

| Exit | Meaning | Data changed? |
|---|---|---|
| 0 | Profile deleted, audit row written | yes (the one profile) |
| 1 | `No matching profile; nothing deleted`, or a connection/SQL error (`Deletion failed: <ExceptionType>`) | no (transaction not committed) |
| 2 | Missing `DATABASE_URL_RETENTION`, invalid UUID (argparse), or target guard refusal | no |

The tool never loads `.env`, and refuses to fall back to `DATABASE_URL`.

## 2. Hard rules

1. Only one DB URL is ever used: the one you set explicitly as `DATABASE_URL_RETENTION`
   for that single command. The CLI accepts only one loopback address and a database
   name containing a separate `test`, `drill`, `disposable`, or `pytest` token; query
   strings and multi-host URLs are refused. It verifies the connected database/server
   address before calling the deletion function. This is defense in depth, not proof of
   server identity; perform the read-only checks below as well.
2. Production targets are intentionally unsupported by this CLI. A separate reviewed
   design and explicit approval are required before enabling any such path.
3. Never read or print `.env`. Never copy DB URLs or passwords into chat, tickets or logs.
4. Do **not** run `tools/purge_expired_contacts.py` (legacy purge) for this workflow.
5. Do **not** run `tools/setup_db_roles.py` for a rehearsal or a deletion. It reads
   `.env`, rotates role passwords and rewrites `.env`. It is a production role change.
5. Do **not** use `DATABASE_URL_ADMIN` / the migration role for a deletion.
6. Do not run the pytest integration suite against a production URL. Integration tests
   only use the guarded disposable fixture (section 6).
7. Deletion is irreversible. Do not run it for an unverified identity, a guessed UUID,
   or a test profile on a production DB.

## 3. Target verification (read-only, before any write)

Run this against the URL you intend to use. Abort unless every check passes.

```sh
psql "$TARGET_URL" -X -A -t -c "select current_database(), inet_server_addr(), inet_server_port(), current_setting('data_directory')"
```

Checks:

- `current_database()` is the disposable/expected DB name (not the production DB name).
- `inet_server_addr()` / `inet_server_port()` are the endpoint you expect (for a
  rehearsal: `127.0.0.1` on the port of the cluster you started yourself).
- `current_setting('data_directory')` is the data directory of the disposable cluster.
  For a production target, stop: production deletions need the separate approval.
- Privileges are as designed (read-only):

```sql
select has_function_privilege('app_retention','public.delete_profile_on_request(uuid)','EXECUTE') as retention_can_execute,   -- expect t
       has_function_privilege('public','public.delete_profile_on_request(uuid)','EXECUTE') as public_can_execute,               -- expect f
       has_table_privilege('app_retention','profil','DELETE') as retention_can_delete_profil;                                    -- expect f
```

- Before deleting, confirm the identity verification was done by the operator outside
  the tool (the tool trusts the UUID it is given). Record the ticket reference.

## 4. Execution

Set the URL only for this command, without echoing it:

```sh
cd /data/projects/FoerderRadar-live
env -u DATABASE_URL -u DATABASE_URL_ADMIN -u PGHOST -u PGHOSTADDR \
  -u PGPORT -u PGDATABASE -u PGSERVICE -u PGSERVICEFILE \
  DATABASE_URL_RETENTION="<verified loopback disposable DB URL>" \
  python3 tools/delete_profile_on_request.py <kunde_id-uuid>; echo "exit=$?"
```

The command clears common PostgreSQL connection overrides; the CLI also pins target
fields and ignores service/passfile routing. Never put credentials in shell history.

## 5. Post-check (read-only)

```sql
select 'profil', count(*) from profil where kunde_id = '<uuid>'
union all select 'kontakt', count(*) from kontakt where kunde_id = '<uuid>'
union all select 'match', count(*) from match where kunde_id = '<uuid>'
union all select 'versand', count(*) from versand where kunde_id = '<uuid>'
union all select 'audit', count(*) from profile_deletion_audit where kunde_id = '<uuid>';
```

Expected after exit 0: `profil`, `kontakt`, `match`, `versand` = 0 and `audit` = 1.
Running the tool again for the same UUID must give exit 1 (`No matching profile`) and
must not add a second audit row. If you see anything else, stop and escalate.

## 6. Failure handling

- Exit 1 with `No matching profile`: the UUID does not exist (or was already deleted).
  Do not retry blindly; re-check the UUID against the verified request.
- Exit 1 with `Deletion failed: <Type>`: the transaction was rolled back. Nothing was
  deleted. Check the target and the function/privileges (section 3), then escalate.
- Exit 2: fix the environment or the UUID. Nothing was changed.
- Wrong profile deleted: there is no undo in this workflow. Restore only from the
  verified backup, into a separate clone first, and escalate to the data owner.

Integration tests for the function exist and must stay green:
`tests/pytest/test_db_integration.py::test_requested_profile_deletion_ignores_retention_deadline`.
They use the guarded fixture in `tests/pytest/conftest.py`
(`FOERDER_RUN_DB_TESTS=1 FOERDER_TEST_DB_BACKEND=local`, or `service` in CI with a
loopback admin URL to a fixture-owned PostgreSQL). Set `FOERDER_TESTING=1` for any pytest
run that imports app code: otherwise `app/main.py` loads the repo `.env` and overrides
the process environment.

## 7. Known gaps

- The CLI guard is a local interlock, not proof of database identity: local forwarding
  or proxies can still route traffic unexpectedly. Keep the read-only target checks
  in section 3 and verify the PostgreSQL identity before any approved use. The guard
  does not provide authorization.
- The tool does not check that the function exists. A missing function surfaces as
  `Deletion failed: UndefinedFunction` (exit 1).
- Activation of public intake/deletion forms and any production migration are out of
  scope and still pending owner approval.

## 8. Rehearsal procedure (disposable cluster)

Reproduces sections 3–5 on a cluster that you create and stop yourself. Use a workspace
scratch directory, not the repo root.

1. `initdb -D <scratch>/data -U drill_admin --auth-local=trust --auth-host=trust`
2. `pg_ctl -D <scratch>/data -l <scratch>/server.log -w -o "-p <free-port> -c listen_addresses=127.0.0.1 -c unix_socket_directories=<scratch>/sock -c fsync=off" start`
3. Verify target (section 3): `data_directory` must be `<scratch>/data`.
4. `createdb` a disposable DB (e.g. `foerderradar_drill`), then
   `psql -v ON_ERROR_STOP=1 -f db/init.sql`, and
   `-f db/migrations/20261018_consent_retention_metadata.sql` and
   `-f db/migrations/20261019_request_deletion.sql` (both idempotent).
5. Create a LOGIN role `app_retention` and grant only what `setup_db_roles.py` grants for
   deletion: `USAGE` on schema `public`, `EXECUTE` on `delete_profile_on_request(uuid)`,
   `INSERT` on `profile_deletion_audit`. Do not run `setup_db_roles.py` itself.
6. Seed a target profile (with a future `loeschdatum`, linked kontakt/match/versand) and a
   control profile.
7. Run the tool as in section 4 with `DATABASE_URL_RETENTION` pointing at the drill DB.
8. Run section 5 checks, and verify that the control profile is unchanged.
9. `pg_ctl -D <scratch>/data -m fast stop`, then delete `<scratch>` completely.

## Rehearsal record

Date: 2026-10-19 (Europe/Berlin). Branch `develop`. No commit made.

- Environment: fresh PostgreSQL 16.15 cluster created by the operator session in
  `.openclaw/tmp/deletion-drill/`, bound to `127.0.0.1:55439` (unix socket in the same
  scratch dir), trust auth, role `drill_admin`. Own process, own data dir, no shared
  service or container touched. DB `foerderradar_drill`.
- Preflight: `data_directory` and port matched the scratch cluster before the DB was created.
- Schema: `db/init.sql`, then both migrations, applied with `ON_ERROR_STOP=1` (only
  `already exists, skipping` notices). `delete_profile_on_request` is `SECURITY DEFINER`;
  `has_function_privilege('public', ...)` = `f`.
- Privileges: `app_retention` can execute the function (`t`), cannot DELETE `profil` (`f`),
  cannot read `kontakt` (`f`).
- Tool runs:
  - no `DATABASE_URL_RETENTION` → `exit=2`
  - `not-a-uuid` → argparse error, `exit=2`
  - target UUID → `Deleted profile ... exit=0`
  - same UUID again → `No matching profile; nothing deleted`, `exit=1`
  - unknown UUID → `No matching profile; nothing deleted`, `exit=1`
- Post-check: target rows in `profil`/`kontakt`/`match`/`versand` = 0; control rows in
  `profil`/`kontakt`/`match` = 1 each; `profile_deletion_audit` = 1 row for the target UUID
  (columns: `kunde_id`, `requested_at`, `deleted_at`).
- At this revision, the target-guard unit tests and fail-closed selector integration
  test pass; the full local verification counts are recorded in the current change review.
  The deletion rehearsal above predates these code changes.
- Cleanup: drill cluster stopped and its scratch directory removed. Rerun the deletion
  rehearsal against the revised CLI before any future operator use.

## 9. Live mode (added 2026-10-30)

The default mode above (loopback test/drill DB only) is unchanged. For a verified
request on the live database the CLI has an explicit `--live` mode:

```sh
DATABASE_URL_RETENTION=<app_retention URL> python3 tools/delete_profile_on_request.py <kunde_id> \
  --live --confirm-id <kunde_id> --confirm-db foerderradar
```

- It refuses unless `--confirm-id` repeats the UUID, `--confirm-db` repeats `foerderradar`,
  the URL names the database `foerderradar`, has exactly one host and no query
  parameters, and `current_database()` matches after connecting.
- Request flow: request arrives at team@foerdora.cloud -> verify the requester -> find
  the profile (`select kunde_id from kontakt where lower(email)=lower('<mail>')`, with the
  admin role, never copy contact data elsewhere) -> run the command above -> reply to the
  requester. The reply deadline is not set by this tool.
- Do not request health or disability details by mail.
- Live test 2026-10-30: a synthetic profile with `kontakt`, `profil_agent`, `match` and
  `versand` rows was found by its mail address and deleted; all rows were gone, one audit
  row (UUID + timestamps) remained, total contacts unchanged. A second run reported
  "No matching profile". This does not replace the operator's own legal review.

### Operator steps per request (live)

1. **Check the sender.** Operator rule: a deletion request is only accepted from the
   same mail address the customer used to register with Fördora (the address stored in
   `kontakt`). A request from another address is not acted on; reply that it must be
   sent from the registered address, or that the requester must confirm their identity
   in another way if the address is no longer used (the operator decides the proof case
   by case). Never ask for health or disability details.
2. **Find the profile** by mail address (see above). Exactly one match is expected;
   otherwise stop and clarify.
3. **Delete** with the `--live` command above.
4. **Reply to the requester** that the data has been deleted, with the date. Do not
   include other personal data in the reply.
5. **Deadline:** answer without undue delay, at the latest within one month (GDPR
   Art. 12(3); extendable by two months in complex cases if the requester is told within
   the first month). General information, not legal advice; the tool sends no reply and
   enforces no deadline.

## 10. Automatische Widerrufe per Mail (added 2026-10-31)

- Migration: `db/migrations/20261031_withdraw_by_email.sql` (idempotent, nach Backup, Admin-Rolle), danach
  `GRANT EXECUTE ON FUNCTION public.withdraw_by_email(text) TO app_retention;`
- Lauf: `FOERDER_FROM=team@foerdora.cloud HIMALAYA_ACCOUNT=foerdora DATABASE_URL_RETENTION=… python3 tools/process_withdrawals.py` = Dry-Run; `--apply` löscht, bestätigt und merkt.
- Mit `--apply` bricht das Skript vor jeder Löschung ab (Exit 2), wenn `FOERDER_FROM` nicht auf foerdora.cloud zeigt.
- Exit-Codes: 0 ok, 3 = Mails zur manuellen Prüfung vorhanden (nichts gelöscht), 1 = Fehler.
- Manuelle Fälle wie bisher nach Abschnitt 9 bearbeiten.
