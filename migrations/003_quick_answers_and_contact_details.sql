-- Contact email, tenant pack settings, editable quick answers with automatic history (D-015).

-- 1. Email on contacts. The app normalizes it (P2.1b); the database enforces the basics.
ALTER TABLE contacts ADD COLUMN email text
    CHECK (length(email) <= 254 AND email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$');

-- 2. Per-tenant values the industry pack asks for (e.g. study_abroad: served_countries).
ALTER TABLE tenants ADD COLUMN settings jsonb NOT NULL DEFAULT '{}'
    CHECK (jsonb_typeof(settings) = 'object');

-- 3. Quick answers: fixed replies to button taps and common typed questions, no AI.
--    Edited by the operator (any tenant) or the tenant's admin (own tenant only; enforced in P6).

-- {"en": "...", "bn": "..."}: non-empty text per 2-letter language code.
CREATE FUNCTION quick_answer_answers_ok(answers jsonb) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_typeof(answers) = 'object' AND NOT EXISTS (
        SELECT 1 FROM jsonb_each(answers) AS e
        WHERE e.key !~ '^[a-z]{2}$'
           OR jsonb_typeof(e.value) <> 'string'
           OR btrim(e.value #>> '{}') = ''
    )
$$;

-- Triggers arrive already normalized by the app: non-empty, trimmed, lower-case.
CREATE FUNCTION quick_answer_triggers_ok(triggers text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT NOT EXISTS (
        SELECT 1 FROM unnest(triggers) AS t WHERE t = '' OR t <> btrim(t) OR t <> lower(t)
    )
$$;

CREATE FUNCTION quick_answer_codes_ok(codes text[]) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT NOT EXISTS (SELECT 1 FROM unnest(codes) AS c WHERE c !~ '^[A-Z][A-Z0-9_]{1,39}$')
$$;

CREATE TABLE quick_answers (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  bigint      NOT NULL REFERENCES tenants (id),
    code       text        NOT NULL CHECK (code ~ '^[A-Z][A-Z0-9_]{1,39}$'),  -- button payload
    triggers   text[]      NOT NULL DEFAULT '{}' CHECK (quick_answer_triggers_ok(triggers)),
    answers    jsonb       NOT NULL DEFAULT '{}' CHECK (quick_answer_answers_ok(answers)),
    buttons    text[]      NOT NULL DEFAULT '{}' CHECK (quick_answer_codes_ok(buttons)),
    action     text        CHECK (action IN ('start_booking')),
    active     boolean     NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (action IS NOT NULL OR answers <> '{}'::jsonb),  -- must say something or do something
    UNIQUE (tenant_id, code),
    UNIQUE (tenant_id, id)
);
CREATE TRIGGER quick_answers_updated_at BEFORE UPDATE ON quick_answers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- One trigger phrase → one quick answer per tenant ("fees" can't be ambiguous). Checked in a
-- trigger because it spans rows; a per-tenant lock makes two admins saving at once safe.
-- Inactive rows keep their phrases reserved, so switching them back on can't collide.
CREATE FUNCTION quick_answers_unique_triggers() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    clash text;
BEGIN
    PERFORM pg_advisory_xact_lock(733, (NEW.tenant_id % 2147483647)::integer);
    SELECT t INTO clash FROM unnest(NEW.triggers) AS t GROUP BY t HAVING count(*) > 1 LIMIT 1;
    IF clash IS NOT NULL THEN
        RAISE unique_violation USING MESSAGE = format('trigger "%s" is listed twice', clash);
    END IF;
    SELECT t INTO clash
    FROM quick_answers AS q, unnest(q.triggers) AS t
    WHERE q.tenant_id = NEW.tenant_id AND q.id <> NEW.id AND t = ANY (NEW.triggers)
    LIMIT 1;
    IF clash IS NOT NULL THEN
        RAISE unique_violation
            USING MESSAGE = format('trigger "%s" already belongs to another quick answer', clash);
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER quick_answers_unique_triggers BEFORE INSERT OR UPDATE ON quick_answers
    FOR EACH ROW EXECUTE FUNCTION quick_answers_unique_triggers();

-- 4. History, written by the database itself so no edit can skip it. Survives deletion of
--    the quick answer (plain id, no FK), so any change can be undone. Who changed it comes
--    from the transaction setting app.user_id (NULL = system).
CREATE TABLE quick_answer_history (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint      NOT NULL REFERENCES tenants (id),
    quick_answer_id bigint      NOT NULL,
    operation       text        NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
    before          jsonb,
    after           jsonb,
    changed_by      bigint      REFERENCES users (id),
    changed_at      timestamptz NOT NULL DEFAULT now(),
    CHECK ((operation = 'insert') = (before IS NULL)),
    CHECK ((operation = 'delete') = (after IS NULL))
);
CREATE INDEX quick_answer_history_tenant ON quick_answer_history (tenant_id, changed_at DESC);
CREATE INDEX quick_answer_history_answer ON quick_answer_history (quick_answer_id, id);

CREATE FUNCTION quick_answers_history() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO quick_answer_history (tenant_id, quick_answer_id, operation, before, after, changed_by)
    VALUES (
        coalesce(NEW.tenant_id, OLD.tenant_id),
        coalesce(NEW.id, OLD.id),
        lower(TG_OP),
        CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
        CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END,
        nullif(current_setting('app.user_id', true), '')::bigint
    );
    RETURN NULL;
END;
$$;
CREATE TRIGGER quick_answers_history AFTER INSERT OR UPDATE OR DELETE ON quick_answers
    FOR EACH ROW EXECUTE FUNCTION quick_answers_history();
