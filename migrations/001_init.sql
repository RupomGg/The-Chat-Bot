-- Core schema (PRD §10). Rules that keep data valid live here, not only in app code.
--
-- Tenant isolation (D-010): every parent table has UNIQUE (tenant_id, id), and children
-- reference it with a composite foreign key (tenant_id, parent_id). The database itself
-- then refuses a row that links one client's data to another client's.
-- Foreign keys use the default NO ACTION: deleting a tenant that still has data fails
-- instead of silently deleting it.

CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TABLE tenants (
    id                         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug                       text        NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,39}$'),
    name                       text        NOT NULL CHECK (btrim(name) <> ''),
    country_code               text        NOT NULL DEFAULT 'BD' CHECK (country_code ~ '^[A-Z]{2}$'),
    timezone                   text        NOT NULL DEFAULT 'Asia/Dhaka' CHECK (btrim(timezone) <> ''),
    currency                   text        NOT NULL DEFAULT 'BDT' CHECK (currency ~ '^[A-Z]{3}$'),
    languages                  text[]      NOT NULL DEFAULT '{}',
    data_region                text        NOT NULL DEFAULT 'singapore'
                                           CHECK (data_region IN ('singapore', 'eu')),
    model                      text        NOT NULL DEFAULT 'claude-haiku-4-5'
                                           CHECK (model ~ '^(claude|gemini)-[a-z0-9.-]+$'),
    cache_ttl                  text        NOT NULL DEFAULT '5m' CHECK (cache_ttl IN ('5m', '1h')),
    monthly_conversation_quota integer     NOT NULL DEFAULT 500 CHECK (monthly_conversation_quota > 0),
    hard_cap                   integer     NOT NULL DEFAULT 1000,
    bot_pause_hours            integer     NOT NULL DEFAULT 24 CHECK (bot_pause_hours BETWEEN 1 AND 168),
    allowed_origins            text[]      NOT NULL DEFAULT '{}',
    widget_theme               jsonb       NOT NULL DEFAULT '{}'
                                           CHECK (jsonb_typeof(widget_theme) = 'object'),
    fallback_text              text        NOT NULL CHECK (btrim(fallback_text) <> ''),
    crm_webhook_url            text        CHECK (crm_webhook_url ~ '^https://'),
    crm_webhook_secret_enc     bytea,
    active                     boolean     NOT NULL DEFAULT true,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    CHECK (hard_cap >= monthly_conversation_quota),
    CHECK ((crm_webhook_url IS NULL) = (crm_webhook_secret_enc IS NULL))
);

CREATE TABLE knowledge_versions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint      NOT NULL REFERENCES tenants (id),
    content      text        NOT NULL CHECK (btrim(content) <> ''),
    token_count  integer     NOT NULL CHECK (token_count >= 0),
    eval_passed  boolean     NOT NULL DEFAULT false,
    published_at timestamptz,
    created_by   text        NOT NULL CHECK (btrim(created_by) <> ''),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (published_at IS NULL OR eval_passed)  -- publish gate (PRD §6.5 F37)
);
CREATE INDEX knowledge_versions_tenant ON knowledge_versions (tenant_id, created_at DESC);

CREATE TABLE branches (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  bigint      NOT NULL REFERENCES tenants (id),
    name       text        NOT NULL CHECK (btrim(name) <> ''),  -- "Online" is a branch row
    address    text,
    maps_url   text        CHECK (maps_url ~ '^https://'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX branches_tenant_name ON branches (tenant_id, lower(name));

CREATE TABLE schedules (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    bigint  NOT NULL,
    branch_id    bigint  NOT NULL,
    weekday      smallint NOT NULL CHECK (weekday BETWEEN 1 AND 7),  -- ISO: 1 = Monday
    start_time   time    NOT NULL,
    end_time     time    NOT NULL,
    slot_minutes integer NOT NULL CHECK (slot_minutes BETWEEN 10 AND 240),
    capacity     integer NOT NULL CHECK (capacity > 0),
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (end_time > start_time),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches (tenant_id, id)
);
CREATE INDEX schedules_tenant ON schedules (tenant_id, branch_id);

CREATE TABLE holidays (
    tenant_id bigint NOT NULL REFERENCES tenants (id),
    date      date   NOT NULL,
    PRIMARY KEY (tenant_id, date)
);

CREATE TABLE events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   bigint      NOT NULL REFERENCES tenants (id),
    title       text        NOT NULL CHECK (btrim(title) <> ''),
    starts_at   timestamptz NOT NULL,
    branch_id   bigint,
    capacity    integer     CHECK (capacity > 0),
    description text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches (tenant_id, id)
);
CREATE INDEX events_tenant ON events (tenant_id, starts_at);

CREATE TABLE channels (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint      NOT NULL REFERENCES tenants (id),
    type           text        NOT NULL CHECK (type IN ('web', 'telegram', 'messenger', 'whatsapp')),
    external_id    text        CHECK (btrim(external_id) <> ''),  -- page id / phone_number_id / bot id
    secret_enc     bytea,      -- Fernet-encrypted credentials
    webhook_secret text,
    active         boolean     NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (type = 'web' OR external_id IS NOT NULL),
    UNIQUE (type, external_id),
    UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX channels_one_web_per_tenant ON channels (tenant_id) WHERE type = 'web';

CREATE TABLE users (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id     bigint      REFERENCES tenants (id),  -- NULL = operator (us)
    email         text        NOT NULL CHECK (email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'),
    password_hash text        NOT NULL CHECK (password_hash <> ''),
    role          text        NOT NULL CHECK (role IN ('operator', 'tenant_admin', 'counsellor')),
    active        boolean     NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CHECK ((role = 'operator') = (tenant_id IS NULL)),
    UNIQUE (tenant_id, id)
);
CREATE UNIQUE INDEX users_email ON users (lower(email));
CREATE INDEX users_tenant ON users (tenant_id);

CREATE TABLE contacts (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id        bigint      NOT NULL,
    channel_id       bigint      NOT NULL,
    external_user_id text        NOT NULL CHECK (btrim(external_user_id) <> ''),
    name             text,
    phone            text        CHECK (phone ~ '^\+[1-9][0-9]{7,14}$'),  -- E.164
    adult            boolean,    -- NULL = not asked yet
    profile          jsonb       NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(profile) = 'object'),
    score            text        NOT NULL DEFAULT 'cold' CHECK (score IN ('hot', 'warm', 'cold')),
    flags            text[]      NOT NULL DEFAULT '{}',
    status           text        NOT NULL DEFAULT 'new' CHECK (status IN (
                         'new', 'contacted', 'counselling_booked', 'counselled',
                         'applied', 'enrolled', 'lost')),
    assignee_user_id bigint,
    source_ad        jsonb       CHECK (jsonb_typeof(source_ad) = 'object'),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (adult IS DISTINCT FROM false OR phone IS NULL),  -- minors: no phone stored (PDP Act)
    UNIQUE (channel_id, external_user_id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, channel_id) REFERENCES channels (tenant_id, id),
    FOREIGN KEY (tenant_id, assignee_user_id) REFERENCES users (tenant_id, id)
);
CREATE INDEX contacts_tenant ON contacts (tenant_id, created_at DESC);
CREATE TRIGGER contacts_updated_at BEFORE UPDATE ON contacts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE conversations (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         bigint      NOT NULL,
    contact_id        bigint      NOT NULL,
    state             text        NOT NULL DEFAULT 'bot' CHECK (state IN ('bot', 'human', 'closed')),
    paused_until      timestamptz,
    unanswered_streak integer     NOT NULL DEFAULT 0 CHECK (unanswered_streak >= 0),
    window_expires_at timestamptz,
    last_message_at   timestamptz NOT NULL DEFAULT now(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, contact_id) REFERENCES contacts (tenant_id, id)
);
CREATE INDEX conversations_tenant ON conversations (tenant_id, last_message_at DESC);
CREATE INDEX conversations_contact ON conversations (contact_id, last_message_at DESC);

CREATE TABLE messages (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id          bigint        NOT NULL,
    conversation_id    bigint        NOT NULL,
    role               text          NOT NULL CHECK (role IN ('student', 'bot', 'staff', 'system')),
    content            text          NOT NULL CHECK (content <> ''),
    external_id        text,         -- channel message id, for idempotency
    model              text,         -- 'quick' for quick answers (PRD §6.8)
    input_tokens       integer       CHECK (input_tokens >= 0),
    cache_read_tokens  integer       CHECK (cache_read_tokens >= 0),
    cache_write_tokens integer       CHECK (cache_write_tokens >= 0),
    output_tokens      integer       CHECK (output_tokens >= 0),
    cost_usd           numeric(10,6) CHECK (cost_usd >= 0),
    created_at         timestamptz   NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, external_id),  -- NULLs don't collide
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);
CREATE INDEX messages_conversation ON messages (conversation_id, created_at);
CREATE INDEX messages_tenant ON messages (tenant_id, created_at);

CREATE TABLE bookings (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint      NOT NULL,
    contact_id     bigint      NOT NULL,
    branch_id      bigint      NOT NULL,
    slot_start     timestamptz NOT NULL,
    status         text        NOT NULL DEFAULT 'booked'
                               CHECK (status IN ('booked', 'cancelled', 'attended', 'no_show')),
    reminder_state text        NOT NULL DEFAULT 'none'
                               CHECK (reminder_state IN ('none', 'day_before_sent', 'hour_before_sent')),
    created_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, contact_id) REFERENCES contacts (tenant_id, id),
    FOREIGN KEY (tenant_id, branch_id) REFERENCES branches (tenant_id, id)
);
CREATE UNIQUE INDEX bookings_no_double ON bookings (contact_id, slot_start) WHERE status = 'booked';
CREATE INDEX bookings_tenant ON bookings (tenant_id, slot_start);
CREATE INDEX bookings_slot ON bookings (branch_id, slot_start) WHERE status = 'booked';

CREATE TABLE event_registrations (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  bigint      NOT NULL,
    event_id   bigint      NOT NULL,
    contact_id bigint      NOT NULL,
    status     text        NOT NULL DEFAULT 'registered'
                           CHECK (status IN ('registered', 'cancelled', 'attended')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, contact_id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES events (tenant_id, id),
    FOREIGN KEY (tenant_id, contact_id) REFERENCES contacts (tenant_id, id)
);
CREATE INDEX event_registrations_tenant ON event_registrations (tenant_id, created_at);

CREATE TABLE notes (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  bigint      NOT NULL,
    contact_id bigint      NOT NULL,
    user_id    bigint      NOT NULL REFERENCES users (id),  -- staff or operator
    body       text        NOT NULL CHECK (btrim(body) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, contact_id) REFERENCES contacts (tenant_id, id)
);
CREATE INDEX notes_tenant ON notes (tenant_id, contact_id, created_at);

CREATE TABLE jobs (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind         text        NOT NULL CHECK (btrim(kind) <> ''),
    payload      jsonb       NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(payload) = 'object'),
    run_at       timestamptz NOT NULL DEFAULT now(),
    attempts     integer     NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer     NOT NULL DEFAULT 6 CHECK (max_attempts > 0),
    status       text        NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'running', 'done', 'dead')),
    last_error   text,
    locked_at    timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK (attempts <= max_attempts)
);
CREATE INDEX jobs_queue ON jobs (status, run_at);

CREATE TABLE audit_events (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id       bigint      REFERENCES tenants (id),  -- NULL = system-wide event
    conversation_id bigint,
    kind            text        NOT NULL CHECK (btrim(kind) <> ''),
    detail          jsonb       NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(detail) = 'object'),
    created_at      timestamptz NOT NULL DEFAULT now(),
    -- A composite FK isn't checked when any column is NULL, so a global event must not
    -- point at a conversation (it would bypass the tenant match).
    CHECK (conversation_id IS NULL OR tenant_id IS NOT NULL),
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);
CREATE INDEX audit_events_tenant ON audit_events (tenant_id, created_at DESC);

CREATE TABLE wa_billable (
    tenant_id bigint  NOT NULL REFERENCES tenants (id),
    month     date    NOT NULL CHECK (extract(day FROM month) = 1),
    category  text    NOT NULL CHECK (category IN ('service', 'utility', 'marketing', 'authentication')),
    count     integer NOT NULL DEFAULT 0 CHECK (count >= 0),
    PRIMARY KEY (tenant_id, month, category)
);
