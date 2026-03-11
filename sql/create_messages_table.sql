CREATE TABLE IF NOT EXISTS messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    userid BIGINT NOT NULL,
    username TEXT,
    firstname TEXT,
    lastname TEXT,
    message TEXT NOT NULL,
    timecreated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    check1_time TIMESTAMPTZ,
    check1_res TEXT,
    check1_is_text BOOLEAN NOT NULL DEFAULT FALSE,
    check2_time TIMESTAMPTZ,
    check2_res TEXT,
    check2_is_text BOOLEAN NOT NULL DEFAULT FALSE,
    check3_time TIMESTAMPTZ,
    check3_res TEXT,
    check3_is_text BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_messages_userid ON messages(userid);
CREATE INDEX IF NOT EXISTS idx_messages_timecreated ON messages(timecreated);
