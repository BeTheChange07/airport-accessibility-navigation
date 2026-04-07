-- =============================================================
-- Refresh amenities.nodeID to point at the nearest nav_node by
-- the amenity's own lat/lng. Run this after any nav_nodes
-- re-import or recalibration so routing destinations stop
-- pointing at stale nodes.
--
-- This is non-destructive: it only updates the nodeID column.
-- status / crowdLevel / wheelChairAccessible are preserved.
-- =============================================================

BEGIN;

-- Sanity: how many amenities currently link to a node that is
-- more than ~30 meters away from the amenity's own coordinates?
-- (~30m at lat ≈ 32.9 → (30/111320)^2 ≈ 7.3e-8 deg²)
SELECT COUNT(*) AS stale_links_before
FROM amenities a
JOIN nav_nodes n ON n.id = a.nodeID
WHERE (n.lat - a.latitude)^2 + (n.lng - a.longitude)^2 > 7.3e-8;

-- Re-link every amenity to its closest nav_node by Euclidean distance
-- over (lat, lng). Same formula as import_amenities.sql so behavior
-- stays consistent.
--
-- IMPORTANT: only relink when the closest nav_node is actually within
-- ~30m. Without this guard, an amenity whose raw coords fall outside
-- the calibrated graph footprint would silently snap onto whatever
-- random edge node happened to be closest (this is what produced the
-- "restroom marker stacked on a far-off node, route walks off the
-- map" bug). Anything farther than 30m is left untouched here; use
-- relink_amenities_with_insert.sql to extend the graph itself for
-- those cases.
UPDATE amenities a
SET nodeID = sub.nearest_id
FROM (
    SELECT a2.id AS amenity_id,
           (SELECT n.id
              FROM nav_nodes n
             WHERE (n.lat - a2.latitude)^2 + (n.lng - a2.longitude)^2 <= 7.3e-8
             ORDER BY (n.lat - a2.latitude)^2 + (n.lng - a2.longitude)^2
             LIMIT 1) AS nearest_id
    FROM amenities a2
) sub
WHERE a.id = sub.amenity_id
  AND sub.nearest_id IS NOT NULL;

-- Same sanity check after the update. In a healthy graph this is 0;
-- a non-zero count means some amenities still sit > 30m from any
-- nav_node and need either nav-editor coverage or a run of
-- relink_amenities_with_insert.sql.
SELECT COUNT(*) AS stale_links_after
FROM amenities a
JOIN nav_nodes n ON n.id = a.nodeID
WHERE (n.lat - a.latitude)^2 + (n.lng - a.longitude)^2 > 7.3e-8;

COMMIT;
