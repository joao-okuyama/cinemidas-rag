PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

INSERT INTO cinemas (
    cinema_id,
    name,
    city,
    state,
    region,
    timezone,
    is_simulated
)
VALUES
    (
        'CV-CIN-001',
        'CineViva Centro',
        'São Paulo',
        'SP',
        'Centro',
        'America/Sao_Paulo',
        1
    ),
    (
        'CV-CIN-002',
        'CineViva Sul',
        'São Paulo',
        'SP',
        'Zona Sul',
        'America/Sao_Paulo',
        1
    ),
    (
        'CV-CIN-003',
        'CineViva Oeste',
        'São Paulo',
        'SP',
        'Zona Oeste',
        'America/Sao_Paulo',
        1
    )
ON CONFLICT (cinema_id) DO NOTHING;

INSERT INTO rooms (
    room_id,
    cinema_id,
    name,
    category
)
VALUES
    ('CV-ROOM-001', 'CV-CIN-001', 'Sala 1', 'STANDARD'),
    ('CV-ROOM-002', 'CV-CIN-001', 'Sala 2', 'VIP'),
    ('CV-ROOM-003', 'CV-CIN-002', 'Sala 1', 'STANDARD'),
    ('CV-ROOM-004', 'CV-CIN-002', 'Sala 2', 'IMAX'),
    ('CV-ROOM-005', 'CV-CIN-003', 'Sala 1', 'STANDARD'),
    ('CV-ROOM-006', 'CV-CIN-003', 'Sala 2', 'VIP')
ON CONFLICT (room_id) DO NOTHING;

INSERT INTO room_formats (
    room_id,
    projection_format
)
VALUES
    ('CV-ROOM-001', '2D'),
    ('CV-ROOM-001', '3D'),
    ('CV-ROOM-002', '2D'),
    ('CV-ROOM-003', '2D'),
    ('CV-ROOM-003', '3D'),
    ('CV-ROOM-004', '2D'),
    ('CV-ROOM-004', '3D'),
    ('CV-ROOM-005', '2D'),
    ('CV-ROOM-006', '2D'),
    ('CV-ROOM-006', '3D')
ON CONFLICT (room_id, projection_format) DO NOTHING;

-- Generate rows A-J and seat numbers 1-12 for each configured room.

WITH RECURSIVE
row_numbers (row_index) AS (
    SELECT 1
    UNION ALL
    SELECT row_index + 1
    FROM row_numbers
    WHERE row_index < 10
),
seat_numbers (seat_number) AS (
    SELECT 1
    UNION ALL
    SELECT seat_number + 1
    FROM seat_numbers
    WHERE seat_number < 12
)
INSERT INTO seats (
    seat_id,
    room_id,
    row_label,
    seat_number
)
SELECT
    rooms.room_id
        || '-'
        || char(64 + row_numbers.row_index)
        || printf('%02d', seat_numbers.seat_number),
    rooms.room_id,
    char(64 + row_numbers.row_index),
    seat_numbers.seat_number
FROM rooms
CROSS JOIN row_numbers
CROSS JOIN seat_numbers
WHERE rooms.room_id IN (
    'CV-ROOM-001',
    'CV-ROOM-002',
    'CV-ROOM-003',
    'CV-ROOM-004',
    'CV-ROOM-005',
    'CV-ROOM-006'
)
ON CONFLICT (seat_id) DO NOTHING;

COMMIT;
