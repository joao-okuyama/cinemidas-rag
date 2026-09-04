-- Migração 003: usuários, reservas temporárias e estrutura do checkout.
-- O executor de migrações controla a transação.

CREATE TABLE users (
    user_id TEXT PRIMARY KEY NOT NULL
        CHECK (length(trim(user_id)) > 0),
    created_at INTEGER NOT NULL
        CHECK (typeof(created_at) = 'integer' AND created_at > 0)
);

CREATE TABLE seat_holds (
    hold_id TEXT PRIMARY KEY NOT NULL
        CHECK (length(trim(hold_id)) > 0),
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'EXPIRED', 'RELEASED', 'CONVERTED')),
    created_at INTEGER NOT NULL
        CHECK (typeof(created_at) = 'integer' AND created_at > 0),
    expires_at INTEGER NOT NULL
        CHECK (
            typeof(expires_at) = 'integer'
            AND expires_at > created_at
        ),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    hold_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL
        CHECK (
            status IN (
                'DRAFT', 'AWAITING_PAYMENT', 'CONFIRMED',
                'EXPIRED', 'CANCELLED'
            )
        ),
    booking_code TEXT UNIQUE,
    subtotal_cents INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(subtotal_cents) = 'integer' AND subtotal_cents >= 0),
    discount_cents INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(discount_cents) = 'integer' AND discount_cents >= 0),
    fee_cents INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(fee_cents) = 'integer' AND fee_cents >= 0),
    total_cents INTEGER NOT NULL DEFAULT 0
        CHECK (typeof(total_cents) = 'integer' AND total_cents >= 0),
    created_at INTEGER NOT NULL
        CHECK (typeof(created_at) = 'integer' AND created_at > 0),
    confirmed_at INTEGER,
    CHECK (total_cents = subtotal_cents - discount_cents + fee_cents),
    CHECK (
        status <> 'CONFIRMED'
        OR (
            booking_code IS NOT NULL
            AND confirmed_at IS NOT NULL
            AND typeof(confirmed_at) = 'integer'
        )
    ),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (hold_id) REFERENCES seat_holds(hold_id) ON DELETE RESTRICT
);

CREATE TABLE session_seats (
    session_id TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'AVAILABLE'
        CHECK (status IN ('AVAILABLE', 'HELD', 'BOOKED')),
    hold_id TEXT,
    order_id TEXT,
    PRIMARY KEY (session_id, seat_id),
    CHECK (
        (status = 'AVAILABLE' AND hold_id IS NULL AND order_id IS NULL)
        OR (status = 'HELD' AND hold_id IS NOT NULL AND order_id IS NULL)
        OR (status = 'BOOKED' AND hold_id IS NULL AND order_id IS NOT NULL)
    ),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE RESTRICT,
    FOREIGN KEY (seat_id) REFERENCES seats(seat_id) ON DELETE RESTRICT,
    FOREIGN KEY (hold_id) REFERENCES seat_holds(hold_id) ON DELETE RESTRICT,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE RESTRICT
);

CREATE TABLE order_items (
    order_item_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    seat_id TEXT NOT NULL,
    ticket_type TEXT NOT NULL CHECK (ticket_type IN ('FULL', 'HALF')),
    base_price_cents INTEGER NOT NULL
        CHECK (typeof(base_price_cents) = 'integer' AND base_price_cents >= 0),
    discount_cents INTEGER NOT NULL
        CHECK (typeof(discount_cents) = 'integer' AND discount_cents >= 0),
    fee_cents INTEGER NOT NULL
        CHECK (typeof(fee_cents) = 'integer' AND fee_cents >= 0),
    total_cents INTEGER NOT NULL
        CHECK (typeof(total_cents) = 'integer' AND total_cents >= 0),
    ticket_code TEXT UNIQUE,
    CHECK (total_cents = base_price_cents - discount_cents + fee_cents),
    UNIQUE (order_id, seat_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE RESTRICT,
    FOREIGN KEY (seat_id) REFERENCES seats(seat_id) ON DELETE RESTRICT
);

CREATE TABLE payments (
    payment_id TEXT PRIMARY KEY NOT NULL,
    order_id TEXT NOT NULL,
    method TEXT NOT NULL
        CHECK (method IN ('PIX_MOCK', 'CARD_MOCK', 'LOYALTY_MOCK')),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    amount_cents INTEGER NOT NULL
        CHECK (typeof(amount_cents) = 'integer' AND amount_cents >= 0),
    idempotency_key TEXT NOT NULL UNIQUE,
    mock_reference TEXT,
    created_at INTEGER NOT NULL
        CHECK (typeof(created_at) = 'integer' AND created_at > 0),
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE RESTRICT
);

CREATE INDEX idx_seat_holds_expiration
ON seat_holds(status, expires_at);

CREATE INDEX idx_seat_holds_user
ON seat_holds(user_id, created_at DESC);

CREATE INDEX idx_session_seats_status
ON session_seats(session_id, status);

CREATE INDEX idx_orders_user_created
ON orders(user_id, created_at DESC);

CREATE INDEX idx_payments_order
ON payments(order_id, created_at DESC);

CREATE TRIGGER session_seat_matches_room_insert
BEFORE INSERT ON session_seats
BEGIN
    SELECT RAISE(ABORT, 'Seat does not belong to the session room.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM sessions AS s
        JOIN seats AS seat ON seat.room_id = s.room_id
        WHERE s.session_id = NEW.session_id
          AND seat.seat_id = NEW.seat_id
    );
END;

CREATE TRIGGER session_seat_matches_room_update
BEFORE UPDATE OF session_id, seat_id ON session_seats
BEGIN
    SELECT RAISE(ABORT, 'Seat does not belong to the session room.')
    WHERE NOT EXISTS (
        SELECT 1
        FROM sessions AS s
        JOIN seats AS seat ON seat.room_id = s.room_id
        WHERE s.session_id = NEW.session_id
          AND seat.seat_id = NEW.seat_id
    );
END;

CREATE TRIGGER held_seat_matches_hold_insert
BEFORE INSERT ON session_seats
WHEN NEW.hold_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Hold does not belong to the session.')
    WHERE NOT EXISTS (
        SELECT 1 FROM seat_holds
        WHERE hold_id = NEW.hold_id
          AND session_id = NEW.session_id
          AND status = 'ACTIVE'
    );
END;

CREATE TRIGGER held_seat_matches_hold_update
BEFORE UPDATE OF status, hold_id ON session_seats
WHEN NEW.hold_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT, 'Hold does not belong to the session.')
    WHERE NOT EXISTS (
        SELECT 1 FROM seat_holds
        WHERE hold_id = NEW.hold_id
          AND session_id = NEW.session_id
          AND status = 'ACTIVE'
    );
END;
