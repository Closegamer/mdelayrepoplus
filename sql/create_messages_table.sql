CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    userid BIGINT NOT NULL,
    username TEXT,
    firstname TEXT,
    lastname TEXT,
    message TEXT NOT NULL,
    message_mode TEXT NOT NULL DEFAULT 'Реальный',
    timecreated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    check1_time TIMESTAMPTZ,
    check1_res TEXT,
    check1_is_text BOOLEAN NOT NULL DEFAULT FALSE,
    check2_time TIMESTAMPTZ,
    check2_res TEXT,
    check2_is_text BOOLEAN NOT NULL DEFAULT FALSE,
    check3_time TIMESTAMPTZ,
    check3_res TEXT,
    check3_is_text BOOLEAN NOT NULL DEFAULT FALSE,
    user_response_text TEXT,
    check1_delay_seconds INTEGER NOT NULL DEFAULT 3600,
    check2_delay_seconds INTEGER NOT NULL DEFAULT 3600,
    check3_delay_seconds INTEGER NOT NULL DEFAULT 3600
);

CREATE INDEX IF NOT EXISTS idx_messages_userid ON messages(userid);
CREATE INDEX IF NOT EXISTS idx_messages_timecreated ON messages(timecreated);
