-- =============================================================
-- Iteration 2 (Build 2) schema snapshot.
--
-- Columns and tables below match what is currently live in RDS.
-- DO NOT re-run this against the live DB -- a teammate already applied
-- these changes by hand. This file exists so a fresh clone of the
-- project can rebuild the schema from scratch after the Build 1 files:
--
--     1. terminal_d_sql-nodes corrected position.sql
--     2. terminal_d_sql-edges corrected position.sql
--     3. upload amenities.sql
--     4. iteration2_amenity_state.sql   (this file)
--     5. relink_amenities.sql
--
-- Iteration 2 use cases and their data:
--   UC5 (Amenity Occupancy): amenityunits + amenities.occupancy
--   UC6 (Crowd Waiting Level): amenities.crowdlevel (0..100)
--   UC7 (Admin Amenity Status): amenities.status (set from admin portal)
-- =============================================================

-- UC5 + UC6: occupancy / last-updated columns on amenities.
ALTER TABLE amenities
    ADD COLUMN IF NOT EXISTS occupancy   TEXT,
    ADD COLUMN IF NOT EXISTS lastupdated TIMESTAMPTZ DEFAULT NOW();

-- UC5: per-stall sensor state.
-- One row per unit (stall / individual room). amenityid FKs the restroom.
CREATE TABLE IF NOT EXISTS amenityunits (
    unitid      INTEGER NOT NULL,
    amenityid   INTEGER NOT NULL REFERENCES amenities(id) ON DELETE CASCADE,
    occupied    BOOLEAN NOT NULL DEFAULT FALSE,
    lastupdated TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (unitid, amenityid)
);

CREATE INDEX IF NOT EXISTS idx_amenityunits_amenityid ON amenityunits(amenityid);
CREATE INDEX IF NOT EXISTS idx_amenities_lastupdated  ON amenities(lastupdated);

-- Seed amenityunits for every restroom that does not yet have stalls.
-- Default: 6 stalls per restroom. Adjust per row in RDS if needed.
INSERT INTO amenityunits (unitid, amenityid, occupied)
SELECT s.i, a.id, FALSE
FROM amenities a
CROSS JOIN generate_series(1, 6) AS s(i)
WHERE a.type = 'restroom'
  AND NOT EXISTS (
      SELECT 1 FROM amenityunits u WHERE u.amenityid = a.id
  );

-- Initial aggregated occupancy from unit states.
UPDATE amenities SET occupancy = 'empty'
WHERE type = 'restroom' AND (occupancy IS NULL OR occupancy = '');
