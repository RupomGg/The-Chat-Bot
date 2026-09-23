-- Records which migration files have been applied. Created by the first migration;
-- app/db.py inserts one row per applied file, in the same transaction as the file.
CREATE TABLE schema_version (
    version    integer     PRIMARY KEY,
    name       text        NOT NULL UNIQUE,
    checksum   text        NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
