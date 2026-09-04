-- Migração 005: estado estruturado da conversa do agente.

CREATE TABLE conversation_sessions (
    conversation_id TEXT PRIMARY KEY NOT NULL
        CHECK (length(trim(conversation_id)) > 0),
    user_id TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'WEB'
        CHECK (channel IN ('WEB', 'WHATSAPP', 'TELEGRAM')),
    state TEXT NOT NULL DEFAULT 'DISCOVERY'
        CHECK (
            state IN (
                'DISCOVERY', 'MOVIE_SELECTED', 'SESSION_SELECTED',
                'SEATS_HELD', 'AWAITING_PAYMENT', 'CONFIRMED'
            )
        ),
    selected_movie_id TEXT,
    selected_cinema_id TEXT,
    selected_session_id TEXT,
    active_hold_id TEXT,
    active_order_id TEXT,
    updated_at INTEGER NOT NULL
        CHECK (typeof(updated_at) = 'integer' AND updated_at > 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (selected_movie_id) REFERENCES movies(movie_id) ON DELETE SET NULL,
    FOREIGN KEY (selected_cinema_id) REFERENCES cinemas(cinema_id) ON DELETE SET NULL,
    FOREIGN KEY (selected_session_id) REFERENCES sessions(session_id) ON DELETE SET NULL,
    FOREIGN KEY (active_hold_id) REFERENCES seat_holds(hold_id) ON DELETE SET NULL,
    FOREIGN KEY (active_order_id) REFERENCES orders(order_id) ON DELETE SET NULL
);

CREATE INDEX idx_conversations_user_updated
ON conversation_sessions(user_id, updated_at DESC);
