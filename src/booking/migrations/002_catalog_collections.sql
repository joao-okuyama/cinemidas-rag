-- Migração 002: evidências das coletas do catálogo.
--
-- O executor de migrações controla a transação.
--
-- Estas tabelas registrarão apenas coletas concluídas com sucesso.
-- A aplicação deverá gravar filmes, evidências e resumo da coleta
-- na mesma transação.
--
-- Instantes: segundos Unix em UTC.
-- Datas de lançamento: texto no formato YYYY-MM-DD.


CREATE TABLE catalog_collections (
    collection_id TEXT PRIMARY KEY NOT NULL
        CHECK (length(trim(collection_id)) > 0),

    provider TEXT NOT NULL
        CHECK (provider = 'tmdb'),

    region TEXT NOT NULL
        CHECK (region = 'BR'),

    collected_at INTEGER NOT NULL
        CHECK (
            typeof(collected_at) = 'integer'
            AND collected_at > 0
        ),

    finished_at INTEGER NOT NULL
        CHECK (
            typeof(finished_at) = 'integer'
            AND finished_at >= collected_at
        ),

    pages_fetched INTEGER NOT NULL
        CHECK (
            typeof(pages_fetched) = 'integer'
            AND pages_fetched > 0
        ),

    movies_processed INTEGER NOT NULL
        CHECK (
            typeof(movies_processed) = 'integer'
            AND movies_processed > 0
        ),

    duplicate_ids INTEGER NOT NULL DEFAULT 0
        CHECK (
            typeof(duplicate_ids) = 'integer'
            AND duplicate_ids >= 0
        )
);


CREATE TABLE catalog_collection_movies (
    collection_id TEXT NOT NULL,
    movie_id TEXT NOT NULL,

    -- Sinal de relevância do TMDB, não bilheteria brasileira.
    -- NULL representa pontuação desconhecida.
    popularity REAL
        CHECK (
            popularity IS NULL
            OR (
                typeof(popularity) IN ('integer', 'real')
                AND popularity >= 0
                AND popularity <= 1.0e308
            )
        ),

    -- Evidência de lançamento cinematográfico brasileiro.
    -- 2 = lançamento limitado; 3 = lançamento regular.
    -- Os dois campos ficam nulos quando não há evidência válida.
    br_release_date TEXT,
    br_release_type INTEGER,

    PRIMARY KEY (collection_id, movie_id),

    FOREIGN KEY (collection_id)
        REFERENCES catalog_collections(collection_id)
        ON DELETE CASCADE,

    FOREIGN KEY (movie_id)
        REFERENCES movies(movie_id)
        ON DELETE RESTRICT,

    CHECK (
        (
            br_release_date IS NULL
            AND br_release_type IS NULL
        )
        OR (
            br_release_date IS NOT NULL
            AND br_release_type IS NOT NULL
            AND typeof(br_release_date) = 'text'
            AND length(br_release_date) = 10
            AND br_release_date GLOB
                '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
            AND typeof(br_release_type) = 'integer'
            AND br_release_type IN (2, 3)
        )
    )
);


CREATE INDEX idx_catalog_collections_latest
ON catalog_collections (
    provider,
    region,
    collected_at DESC,
    finished_at DESC,
    collection_id DESC
);


CREATE INDEX idx_catalog_collection_movies_movie
ON catalog_collection_movies (
    movie_id,
    collection_id
);
