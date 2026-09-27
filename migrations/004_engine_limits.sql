-- Limits the conversation engine enforces (D-018, P4.4).

-- 1. At most this many AI replies per contact per day (tenant's local day); after that a
--    person takes over. Quick answers don't count.
ALTER TABLE tenants ADD COLUMN daily_ai_reply_cap integer NOT NULL DEFAULT 60
    CHECK (daily_ai_reply_cap > 0);

-- 2. Off-topic streak: the AI declined this many requests in a row; at 3 the engine answers
--    with a fixed redirect (no AI call) until redirect_until.
ALTER TABLE conversations
    ADD COLUMN off_topic_streak integer NOT NULL DEFAULT 0 CHECK (off_topic_streak >= 0),
    ADD COLUMN redirect_until timestamptz;
