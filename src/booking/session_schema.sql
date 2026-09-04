PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY NOT NULL,

    movie_id TEXT NOT NULL,
    room_id TEXT NOT NULL,
    projection_format TEXT NOT NULL,

    audio_version TEXT NOT NULL
        CHECK (
            audio_version IN (
                'DUBBED',
                'SUBTITLED',
                'ORIGINAL_PT'
            )
        ),

    status TEXT NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'CANCELLED')),

    starts_at INTEGER NOT NULL
        CHECK (
            typeof(starts_at) = 'integer'
            AND starts_at > 0
        ),

    -- Duration snapshot: later catalog changes must not
    -- silently alter the timing of an existing session.
    runtime_minutes INTEGER NOT NULL
        CHECK (
            typeof(runtime_minutes) = 'integer'
            AND runtime_minutes > 0
        ),

    -- Operational interval before another session may start.
    -- No default: the application must provide this explicitly.
    turnaround_minutes INTEGER NOT NULL
        CHECK (
            typeof(turnaround_minutes) = 'integer'
            AND turnaround_minutes >= 0
        ),

    ends_at INTEGER NOT NULL
        CHECK (typeof(ends_at) = 'integer'),

    room_available_at INTEGER NOT NULL
        CHECK (typeof(room_available_at) = 'integer'),

    full_price_cents INTEGER NOT NULL
        CHECK (
            typeof(full_price_cents) = 'integer'
            AND full_price_cents >= 0
        ),

    -- Base convenience fee per ticket.
    convenience_fee_cents INTEGER NOT NULL
        CHECK (
            typeof(convenience_fee_cents) = 'integer'
            AND convenience_fee_cents >= 0
        ),

    CHECK (
        ends_at = starts_at + runtime_minutes * 60
    ),

    CHECK (
        room_available_at = ends_at + turnaround_minutes * 60
    ),

    FOREIGN KEY (movie_id)
        REFERENCES movies (movie_id)
        ON DELETE RESTRICT,

    -- Also ensures that the selected room supports this projection.
    FOREIGN KEY (room_id, projection_format)
        REFERENCES room_formats (room_id, projection_format)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sessions_movie_start
    ON sessions (movie_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_sessions_room_schedule
    ON sessions (room_id, starts_at, room_available_at)
    WHERE status = 'SCHEDULED';

-- Prevent overlapping room-occupancy intervals.
-- A session may start exactly when the previous room interval ends.

CREATE TRIGGER IF NOT EXISTS sessions_no_overlap_insert
BEFORE INSERT ON sessions
WHEN NEW.status = 'SCHEDULED'
BEGIN
    SELECT RAISE(
        ABORT,
        'Session overlaps an existing room schedule.'
    )
    WHERE EXISTS (
        SELECT 1
        FROM sessions AS existing
        WHERE existing.room_id = NEW.room_id
          AND existing.status = 'SCHEDULED'
          AND NEW.starts_at < existing.room_available_at
          AND NEW.room_available_at > existing.starts_at
    );
END;

-- Apply the same protection to rescheduling and reactivation.

CREATE TRIGGER IF NOT EXISTS sessions_no_overlap_update
BEFORE UPDATE OF
    room_id,
    starts_at,
    room_available_at,
    status
ON sessions
WHEN NEW.status = 'SCHEDULED'
BEGIN
    SELECT RAISE(
        ABORT,
        'Session overlaps an existing room schedule.'
    )
    WHERE EXISTS (
        SELECT 1
        FROM sessions AS existing
        WHERE existing.session_id <> OLD.session_id
          AND existing.room_id = NEW.room_id
          AND existing.status = 'SCHEDULED'
          AND NEW.starts_at < existing.room_available_at
          AND NEW.room_available_at > existing.starts_at
    );
END;

COMMIT;
