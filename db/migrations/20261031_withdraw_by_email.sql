-- Apply with the migration/admin role after a verified backup. Idempotent.
-- Requires 20261019_request_deletion.sql (profile_deletion_audit).
-- Grant EXECUTE to app_retention via tools/setup_db_roles.py (or manually:
--   GRANT EXECUTE ON FUNCTION public.withdraw_by_email(text) TO app_retention;)
CREATE OR REPLACE FUNCTION public.withdraw_by_email(p_email TEXT)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $withdraw$
DECLARE
    v_ids UUID[];
    deleted_count INTEGER;
BEGIN
    -- Widerruf per E-Mail: loescht alle Profile, deren gespeicherte Kontaktadresse
    -- exakt (case-insensitiv) der Absenderadresse entspricht. Gibt nur die Anzahl
    -- zurueck, nie Kontaktdaten. Audit wie delete_profile_on_request (nur UUID).
    IF p_email IS NULL OR strpos(p_email, '@') = 0 THEN
        RETURN 0;
    END IF;
    SELECT array_agg(kunde_id) INTO v_ids
      FROM public.kontakt
     WHERE lower(btrim(email)) = lower(btrim(p_email));
    IF v_ids IS NULL THEN
        RETURN 0;
    END IF;
    DELETE FROM public.profil WHERE kunde_id = ANY (v_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    INSERT INTO public.profile_deletion_audit (kunde_id) SELECT unnest(v_ids);
    RETURN deleted_count;
END;
$withdraw$;
REVOKE ALL ON FUNCTION public.withdraw_by_email(TEXT) FROM PUBLIC;
