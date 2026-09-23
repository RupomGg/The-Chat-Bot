-- Universal core (D-012), performance log (D-013), minors' phones (D-014).
-- 001 is never edited; every change is an upgrade step that keeps existing rows.

-- 1. Industry packs: each tenant runs one pack (study_abroad first). The pack itself is
--    checked by the app's pack loader; here only the name's shape is enforced.
ALTER TABLE tenants
    ADD COLUMN industry text NOT NULL DEFAULT 'study_abroad'
        CHECK (industry ~ '^[a-z][a-z_]{1,39}$');

-- 2. Generic pipeline stages. Each industry pack shows its own labels
--    (e.g. study_abroad: booked = "Counselling booked", in_progress = "Applied").
ALTER TABLE contacts DROP CONSTRAINT contacts_status_check;
UPDATE contacts SET status = CASE status
    WHEN 'counselling_booked' THEN 'booked'
    WHEN 'counselled'         THEN 'in_progress'
    WHEN 'applied'            THEN 'in_progress'
    WHEN 'enrolled'           THEN 'won'
    ELSE status
END;
ALTER TABLE contacts ADD CONSTRAINT contacts_status_check CHECK (status IN (
    'new', 'contacted', 'qualified', 'booked', 'in_progress', 'won', 'lost'));

-- 3. Minors' phone numbers are stored (owner decision D-014, legal risk accepted).
ALTER TABLE contacts DROP CONSTRAINT contacts_check;

-- 4. Performance log: one row per bot reply, metadata only (no message text, no phone).
--    Kept after message text is deleted, so message_id is a plain reference, not an FK.
CREATE TABLE bot_turns (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id          bigint        NOT NULL,
    conversation_id    bigint        NOT NULL,
    message_id         bigint,       -- the bot message this turn produced
    received_at        timestamptz,  -- when the student's message arrived
    source             text          NOT NULL CHECK (source IN ('quick', 'llm', 'fallback', 'handoff')),
    channel            text          NOT NULL CHECK (channel IN ('web', 'telegram', 'messenger', 'whatsapp')),
    model              text,
    language           text          CHECK (language IN ('bn', 'en', 'banglish', 'mixed', 'other')),
    latency_ms         integer       CHECK (latency_ms >= 0),  -- received → reply sent
    llm_ms             integer       CHECK (llm_ms >= 0),      -- time inside the AI call(s)
    input_tokens       integer       CHECK (input_tokens >= 0),
    cache_read_tokens  integer       CHECK (cache_read_tokens >= 0),
    cache_write_tokens integer       CHECK (cache_write_tokens >= 0),
    output_tokens      integer       CHECK (output_tokens >= 0),
    cost_usd           numeric(10,6) CHECK (cost_usd >= 0),
    tool_calls         text[]        NOT NULL DEFAULT '{}',
    stop_reason        text,
    error_code         text          CHECK (length(error_code) <= 100),
    created_at         timestamptz   NOT NULL DEFAULT now(),
    CHECK (source <> 'llm' OR model IS NOT NULL),
    CHECK (source <> 'quick' OR coalesce(cost_usd, 0) = 0),
    FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id)
);
CREATE INDEX bot_turns_tenant ON bot_turns (tenant_id, created_at);
CREATE INDEX bot_turns_conversation ON bot_turns (conversation_id, created_at);

-- Move usage recorded on messages (001) into bot_turns, then keep messages content-only.
INSERT INTO bot_turns (tenant_id, conversation_id, message_id, source, channel, model,
                       input_tokens, cache_read_tokens, cache_write_tokens, output_tokens,
                       cost_usd, created_at)
SELECT m.tenant_id, m.conversation_id, m.id,
       CASE WHEN m.model = 'quick' THEN 'quick' ELSE 'llm' END,
       ch.type,
       CASE WHEN m.model = 'quick' THEN NULL ELSE m.model END,
       m.input_tokens, m.cache_read_tokens, m.cache_write_tokens, m.output_tokens,
       m.cost_usd, m.created_at
FROM messages m
JOIN conversations cv ON cv.id = m.conversation_id
JOIN contacts ct ON ct.id = cv.contact_id
JOIN channels ch ON ch.id = ct.channel_id
WHERE m.role = 'bot' AND m.model IS NOT NULL
ORDER BY m.id;

ALTER TABLE messages
    DROP COLUMN model,
    DROP COLUMN input_tokens,
    DROP COLUMN cache_read_tokens,
    DROP COLUMN cache_write_tokens,
    DROP COLUMN output_tokens,
    DROP COLUMN cost_usd;
