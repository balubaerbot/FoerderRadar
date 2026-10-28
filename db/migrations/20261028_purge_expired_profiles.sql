-- Retention purge function (previously only in db/init.sql, so missing on already-created DBs).
-- Idempotent. Grant EXECUTE to app_retention via tools/setup_db_roles.py.

CREATE OR REPLACE FUNCTION public.purge_expired_profiles()
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $purge$
DECLARE
    deleted_count BIGINT;
BEGIN
    DELETE FROM public.profil AS p
    USING public.kontakt AS k
    WHERE k.kunde_id = p.kunde_id
      AND k.loeschdatum IS NOT NULL
      AND k.loeschdatum <= CURRENT_DATE;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$purge$;
REVOKE ALL ON FUNCTION public.purge_expired_profiles() FROM PUBLIC;
