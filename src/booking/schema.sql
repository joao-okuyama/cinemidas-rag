PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS cinemas (
    cinema_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    city TEXT NOT NULL CHECK (length(trim(city)) > 0),
    state TEXT NOT NULL CHECK (length(state) = 2),
    region TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',

    latitude REAL,
    longitude REAL,

    is_simulated INTEGER NOT NULL DEFAULT 1
        CHECK (is_simulated = 1),

    CHECK (
        (latitude IS NULL AND longitude IS NULL)
        OR
        (
            latitude IS NOT NULL
            AND longitude IS NOT NULL
            AND latitude BETWEEN -90 AND 90
            AND longitude BETWEEN -180 AND 180
        )
    )
);

CREATE TABLE IF NOT EXISTS rooms (
    room_id TEXT PRIMARY KEY NOT NULL,
    cinema_id TEXT NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),

    category TEXT NOT NULL
        CHECK (category IN ('STANDARD', 'VIP', 'IMAX')),

    FOREIGN KEY (cinema_id)
        REFERENCES cinemas (cinema_id)
        ON DELETE RESTRICT,

    UNIQUE (cinema_id, name)
);

CREATE TABLE IF NOT EXISTS room_formats (
    room_id TEXT NOT NULL,

    projection_format TEXT NOT NULL
        CHECK (projection_format IN ('2D', '3D')),

    PRIMARY KEY (room_id, projection_format),

    FOREIGN KEY (room_id)
        REFERENCES rooms (room_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS seats (
    seat_id TEXT PRIMARY KEY NOT NULL,
    room_id TEXT NOT NULL,

    row_label TEXT NOT NULL
        CHECK (
            row_label IN (
                'A', 'B', 'C', 'D', 'E',
                'F', 'G', 'H', 'I', 'J'
            )
        ),

    seat_number INTEGER NOT NULL
        CHECK (
            typeof(seat_number) = 'integer'
            AND seat_number BETWEEN 1 AND 12
        ),

    FOREIGN KEY (room_id)
        REFERENCES rooms (room_id)
        ON DELETE RESTRICT,

    UNIQUE (room_id, row_label, seat_number)
);

CREATE TABLE IF NOT EXISTS movies (
    movie_id TEXT PRIMARY KEY NOT NULL,

    provider TEXT,
    provider_movie_id TEXT,

    title TEXT NOT NULL
        CHECK (length(trim(title)) > 0),

    synopsis TEXT,

    runtime_minutes INTEGER
        CHECK (
            runtime_minutes IS NULL
            OR (
                typeof(runtime_minutes) = 'integer'
                AND runtime_minutes > 0
            )
        ),

    age_rating TEXT,
    source_url TEXT,
    source_updated_at TEXT,

    CHECK (
        (provider IS NULL AND provider_movie_id IS NULL)
        OR
        (
            provider IS NOT NULL
            AND provider_movie_id IS NOT NULL
            AND length(trim(provider)) > 0
            AND length(trim(provider_movie_id)) > 0
        )
    ),

    UNIQUE (provider, provider_movie_id)
);

CREATE INDEX IF NOT EXISTS idx_cinemas_city_region
    ON cinemas (city, region);

CREATE INDEX IF NOT EXISTS idx_movies_title
    ON movies (title);

COMMIT;
