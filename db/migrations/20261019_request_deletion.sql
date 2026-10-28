-- Apply with the migration/admin role after a verified backup.
-- Request deletion has no retention-age condition and cascades linked profile data.
-- PUBLIC cannot execute this function or read/insert into the audit table. Grant
-- function EXECUTE and audit INSERT to app_retention via tools/setup_db_roles.py.
CREATE TABLE IF NOT EXISTS public.profile_deletion_audit (
    kunde_id UUID NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON TABLE public.profile_deletion_audit FROM PUBLIC;

CREATE OR REPLACE FUNCTION public.delete_profile_on_request(p_kunde_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $delete$
DECLARE
    deleted_count BIGINT;
BEGIN
    DELETE FROM public.profil WHERE kunde_id = p_kunde_id;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count = 0 THEN
        RETURN FALSE;
    END IF;
    INSERT INTO public.profile_deletion_audit (kunde_id) VALUES (p_kunde_id);
    RETURN TRUE;
END;
$delete$;
REVOKE ALL ON FUNCTION public.delete_profile_on_request(UUID) FROM PUBLIC;
