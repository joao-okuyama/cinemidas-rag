-- Server-issued guest identities, retry keys and rendered conversation history.
CREATE TABLE guest_sessions (
    token_hash TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    conversation_id TEXT NOT NULL REFERENCES conversation_sessions(conversation_id),
    expires_at INTEGER NOT NULL
);
CREATE TABLE checkout_requests (
    user_id TEXT NOT NULL REFERENCES users(user_id),
    request_id TEXT NOT NULL,
    selection_hash TEXT NOT NULL,
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    PRIMARY KEY (user_id, request_id)
);
ALTER TABLE conversation_sessions ADD COLUMN displayed_options TEXT NOT NULL DEFAULT '{}';
ALTER TABLE conversation_sessions ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;
CREATE TABLE chat_turns (
    conversation_id TEXT NOT NULL REFERENCES conversation_sessions(conversation_id),
    request_id TEXT NOT NULL,
    message TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (conversation_id, request_id)
);
