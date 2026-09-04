ALTER TABLE movies
ADD COLUMN poster_path TEXT
CHECK (
    poster_path IS NULL
    OR (
        typeof(poster_path) = 'text'
        AND length(poster_path) > 1
        AND substr(poster_path, 1, 1) = '/'
        AND substr(poster_path, 2, 1) <> '/'
        AND instr(poster_path, '..') = 0
        AND instr(poster_path, '?') = 0
        AND instr(poster_path, '#') = 0
        AND instr(poster_path, char(92)) = 0
    )
);

CREATE TABLE genres (
    genre_id INT PRIMARY KEY NOT NULL
        CHECK (
            typeof(genre_id) = 'integer'
            AND genre_id > 0
        ),

    name TEXT NOT NULL
        CHECK (
            typeof(name) = 'text'
            AND length(trim(name)) > 0
        )
);

CREATE TABLE movie_genres (
    movie_id TEXT NOT NULL,
    genre_id INTEGER NOT NULL,

    PRIMARY KEY (movie_id, genre_id),

    FOREIGN KEY (movie_id)
        REFERENCES movies(movie_id)
        ON DELETE CASCADE,

    FOREIGN KEY (genre_id)
        REFERENCES genres(genre_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_movie_genres_genre_movie
ON movie_genres (genre_id, movie_id);
