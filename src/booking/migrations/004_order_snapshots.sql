-- Migração 004: snapshots imutáveis das informações exibidas na compra.
-- As colunas são nulas apenas para compatibilidade com bases anteriores.

ALTER TABLE orders ADD COLUMN movie_title TEXT;
ALTER TABLE orders ADD COLUMN cinema_name TEXT;
ALTER TABLE orders ADD COLUMN room_name TEXT;
ALTER TABLE orders ADD COLUMN cinema_timezone TEXT;
ALTER TABLE orders ADD COLUMN session_starts_at INTEGER;
ALTER TABLE orders ADD COLUMN projection_format TEXT;
ALTER TABLE orders ADD COLUMN audio_version TEXT;

ALTER TABLE order_items ADD COLUMN seat_label TEXT;
