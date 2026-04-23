-- =============================================================
-- Iteration 3 data sync.
--
-- Puts data into the existing tables so the live RDS behaves
-- correctly against the current Flask API code (flask-api/app.py)
-- and the mock occupancy sensor (other mock apis/occupancySensors.py).
--
-- No schema changes. No DROPs. Inserts and updates only.
--
-- The real gap this fixes:
--   * amenityunits is 0 rows in RDS, so the admin per-stall flip
--     and the sensor roll-up are silent no-ops. After this runs,
--     every restroom has 6 stall rows so both code paths do work.
--   * amenities rows pre-dating iteration 2 have NULL
--     lastupdated / occupancy; backfill gives clients a real
--     freshness signal and a real starting bucket.
--
-- Idempotent and transactional: safe to re-run; each block skips
-- rows that are already seeded / already non-null.
--
-- Tables left alone: infrastructure, userReports (both 0 rows,
-- not referenced by live code, but we're not dropping them per
-- request).
-- =============================================================

BEGIN;

-- -------------------------------------------------------------
-- 1. Backfill amenities.lastupdated for rows that never had it set
-- -------------------------------------------------------------
UPDATE amenities
   SET lastupdated = NOW()
 WHERE lastupdated IS NULL;

-- -------------------------------------------------------------
-- 2. Initialize amenities.occupancy for restrooms
-- -------------------------------------------------------------
-- Buckets come from occupancySensors.py:
--   'empty' | 'medium' | 'high' | 'full'
-- Start every restroom at 'empty'; the sensor / admin endpoint
-- will update from there.
UPDATE amenities
   SET occupancy = 'empty'
 WHERE type = 'restroom'
   AND (occupancy IS NULL OR occupancy = '');

-- -------------------------------------------------------------
-- 3. Seed amenityunits: 6 stalls per restroom
-- -------------------------------------------------------------
-- Default each stall: vacant, not accessible, stamped NOW().
-- Skips any restroom that already has unit rows, so this is safe
-- to re-run after adding new restrooms later.
INSERT INTO amenityunits (
    amenityid, unitid, unitlabel, unittype,
    wheelchairaccesible, occupied, lastupdated
)
SELECT a.id,
       s.i,
       'Stall ' || s.i,
       'standard',
       FALSE,
       FALSE,
       NOW()
  FROM amenities a
 CROSS JOIN generate_series(1, 6) AS s(i)
 WHERE a.type = 'restroom'
   AND NOT EXISTS (
       SELECT 1 FROM amenityunits u WHERE u.amenityid = a.id
   );

-- Mark stall #1 of each restroom as wheelchair-accessible if the
-- parent amenity claims accessibility. Idempotent: re-running
-- just re-sets TRUE to TRUE.
UPDATE amenityunits u
   SET wheelchairaccesible = TRUE
  FROM amenities a
 WHERE u.amenityid = a.id
   AND u.unitid = 1
   AND LOWER(COALESCE(a.wheelchairaccessible, '')) = 'yes';

-- -------------------------------------------------------------
-- 4. Reconcile amenities.occupancy with the freshly seeded stalls
-- -------------------------------------------------------------
-- All seeded stalls are vacant -> bucket is 'empty'. Only touches
-- restrooms whose bucket is currently NULL or blank, so an
-- already-set bucket (e.g. from the admin portal) is preserved.
UPDATE amenities a
   SET occupancy   = 'empty',
       lastupdated = NOW()
  FROM (
        SELECT amenityid,
               COUNT(*)                                AS total,
               COUNT(*) FILTER (WHERE occupied = TRUE) AS occupied_count
          FROM amenityunits
         GROUP BY amenityid
       ) s
 WHERE a.id = s.amenityid
   AND a.type = 'restroom'
   AND s.total > 0
   AND s.occupied_count = 0
   AND (a.occupancy IS NULL OR a.occupancy = '');

COMMIT;

-- Sanity checks (run after commit to confirm state):
--   SELECT COUNT(*) FROM amenities WHERE lastupdated IS NULL;
--     -> expect 0
--   SELECT COUNT(*) FROM amenities
--    WHERE type = 'restroom' AND (occupancy IS NULL OR occupancy = '');
--     -> expect 0
--   SELECT COUNT(DISTINCT amenityid), COUNT(*) FROM amenityunits;
--     -> expect (# restrooms) and 6 * that
