-- =============================================================
-- Import amenities from DFW Terminal D CSV into the amenities table.
-- Run this in pgAdmin against your postgres database.
--
-- This script:
--   1. Drops & recreates the amenities table
--   2. Inserts each CSV row with auto-classified type
--   3. Links each amenity to the nearest nav_node via nodeID
-- =============================================================

-- Step 1: Recreate the amenities table
DROP TABLE IF EXISTS amenities CASCADE;

CREATE TABLE amenities (
    ID          SERIAL PRIMARY KEY,
    nodeID      INTEGER REFERENCES nav_nodes(id),
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    wheelChairAccessible TEXT DEFAULT 'unknown',
    status      TEXT DEFAULT 'open',
    crowdLevel  INTEGER DEFAULT 0,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION
);

-- Step 2: Load CSV rows into a temp table
CREATE TEMP TABLE csv_import (
    name        TEXT,
    description TEXT,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    altitude    DOUBLE PRECISION
);

INSERT INTO csv_import (name, latitude, longitude) VALUES
('Male Bathroom',       32.8992702, -97.0440495),
('Male Bathroom',       32.8986252, -97.0444645),
('Female Bathroom',     32.8986917, -97.0444042),
('Male Bathroom',       32.8994607, -97.0416537),
('Female Bathroom',     32.8994143, -97.0416521),
('Female Bathroom',     32.8993056, -97.0430806),
('Male Bathroom',       32.8992344, -97.0431683),
('Female Bathroom',     32.8993129, -97.0441102),
('Male Bathroom',       32.8982308, -97.0442769),
('Female Bathroom',     32.898125,  -97.0442777),
('Male Bathroom',       32.8980535, -97.0445593),
('Male Bathroom',       32.8974063, -97.0442786),
('Female Bathroom',     32.8972993, -97.0442779),
('Female Bathroom',     32.897395,  -97.0445636),
('Male Bathroom',       32.8972852, -97.0445877),
('Female Bathroom',     32.8967202, -97.0444579),
('Male Bathroom',       32.8966574, -97.0444073),
('Female Bathroom',     32.8960632, -97.0440944),
('Female Bathroom',     32.8961082, -97.0431817),
('Male Bathroom',       32.8960312, -97.0430821),
('Female Bathroom',     32.8957982, -97.0419206),
('Male Bathroom',       32.8938095, -97.0415756),
('Female Bathroom',     32.8933901, -97.0415826),
('D40',                 32.8995367, -97.0421973),
('D38',                 32.8995389, -97.0423717),
('Point 35',            32.8995344, -97.0429785),
('Escalator',           32.8993684, -97.0435019),
('D34',                 32.8995221, -97.043764),
('D36',                 32.8995373, -97.0431565),
('Elevator',            32.8991334, -97.0438042),
('Escalator',           32.8990529, -97.0438008),
('Escalator',           32.8993761, -97.0440396),
('D33',                 32.8995247, -97.043945),
('D32',                 32.8994684, -97.0445854),
('D30',                 32.8994425, -97.0446129),
('D29',                 32.8994121, -97.0446471),
('D28',                 32.8993254, -97.044751),
('D27',                 32.8990153, -97.044773),
('D25',                 32.8988407, -97.044777),
('Elevator',            32.8993676, -97.0433091),
('D24',                 32.8982852, -97.0448348),
('D23',                 32.8980623, -97.0448428),
('D22',                 32.8972978, -97.0448489),
('D21',                 32.897067,  -97.044861),
('Escalator',           32.896893,  -97.0445485),
('Elevator',            32.8968063, -97.0445405),
('Escalator',           32.8969064, -97.0449623),
('D26',                 32.8965027, -97.0447782),
('Escalator',           32.8962733, -97.0438116),
('Escalator',           32.8960004, -97.0435352),
('Elevator',            32.8960162, -97.0435956),
('Banh Shop',           32.8957832, -97.043486),
('D18',                 32.8963824, -97.0447827),
('D17',                 32.896022,  -97.0447625),
('D16',                 32.8959573, -97.0446881),
('D15',                 32.8959111, -97.0446304),
('D14',                 32.8958334, -97.0445379),
('D12',                 32.8958075, -97.0439505),
('D11',                 32.8958103, -97.0437601),
('D10',                 32.895816,  -97.0431753),
('D8',                  32.8958193, -97.0429809),
('D7',                  32.8958086, -97.0423874),
('D6',                  32.8958092, -97.0422567),
('D5',                  32.8958069, -97.0421876),
('D4',                  32.8940063, -97.0417467),
('D3',                  32.8939309, -97.0417474),
('D2',                  32.8933036, -97.0417531),
('D1',                  32.8932254, -97.0417551),
('Elevator',            32.8962161, -97.0438152),
('Lactation Room',      32.893359,  -97.0415829),
('Lactation Room',      32.8993751, -97.0431913),
('Children''s Play Area by McDonald''s', 32.8956834, -97.0428395),
('DFW Terminal D Interfaith Chapel',     32.9004923, -97.0418359),
('Escalator',           32.8991885, -97.044261),
('Elevator',            32.8990275, -97.0443442),
('Applebee''s Grill + Bar',              32.8960219, -97.0436971),
('American Express Centurion Lounge',    32.8961054, -97.0438172),
('The Wall Street Journal',              32.8959556, -97.0430655),
('Cake Bar',            32.8937915, -97.0416295),
('Trinity Groves Kitchen & Bar',         32.8935955, -97.0417851),
('Lavazza Coffee',      32.8993891, -97.0436087),
('World News & Gifts',  32.8994944, -97.0426752),
('Information Desk',    32.8994183, -97.0438635),
('McDonalds',           32.8993541, -97.0439386),
('TX/MX',               32.899354,  -97.0443291),
('Elevator_D34',        32.8993199, -97.0435896),
('The Italian Kitchen by Wolfgang Puck', 32.8992625, -97.0437841),
('Dickey''s Barbecue Pit',               32.8991555, -97.044578),
('CRU',                 32.8989453, -97.0445821),
('Brewed',              32.8988197, -97.044542),
('Buffalo Wild Wings',  32.8990382, -97.0445132),
('InformationKioskD27', 32.8987445, -97.0446477),
('L''Occitane',         32.8991138, -97.0439369),
('Travel+ Leisure News',32.8988233, -97.0442588),
('M·A·C',              32.8985323, -97.0446173),
('Jo Malone',           32.8985745, -97.0445844),
('Coach',               32.8984435, -97.0447878),
('Longchamp',           32.8983796, -97.044867),
('Chili''s',            32.8982212, -97.0445317),
('MontBlanc',           32.8982059, -97.0448595),
('American Admirals Club',               32.8981755, -97.0448649),
('AmericanAirlinesElevator',             32.8981293, -97.0448434),
('Chanel',              32.8979062, -97.0445919),
('Minute Suites',       32.8981349, -97.0445618),
('Peach Cobbler',       32.8960238, -97.043925),
('Starbucks',           32.8960513, -97.0439652),
('Whataburger',         32.8961372, -97.0441945),
('Chick-fil-A',         32.8963457, -97.0443722),
('Sugarphoria',         32.8961463, -97.0444923),
('Coca-Cola World Experience',           32.8960383, -97.0443702),
('Flying Saucer Draught Emporium',       32.8965099, -97.0445589),
('Subway',              32.8963838, -97.0445792),
('TRG Duty Free',       32.8962554, -97.0445967),
('Lego Store',          32.8965219, -97.0442801),
('7-Eleven',            32.8967532, -97.0445763),
('Be Relax',            32.8970348, -97.0446068),
('Bar Louie',           32.8972054, -97.0445932),
('iStore',              32.8971422, -97.044875),
('Korean Air Lounge',   32.897189,  -97.0448582),
('3Sixty Duty Free',    32.8976763, -97.0449074),
('American Airlines Credit Union Branch and ATM', 32.8983123, -97.0443103),
('Escalator',           32.8978783, -97.0442969),
('Relay',               32.8974916, -97.0442877),
('Hickory - Terminal D',32.897468,  -97.0445928),
('ICE International Currency Exchange',  32.8962569, -97.0440008),
('Eatzi',               32.895901,  -97.0417195),
('360 West Travel Essentials',           32.893423,  -97.0416336),
('TSA Pre Enrollment Center',            32.8991385, -97.0434971);

-- Step 3: Insert into amenities, classifying type and finding nearest nav_node
INSERT INTO amenities (nodeID, name, type, latitude, longitude)
SELECT
    -- Find nearest nav_node by Euclidean distance (fine for nearby points)
    (SELECT n.id FROM nav_nodes n
     ORDER BY (n.lat - c.latitude)^2 + (n.lng - c.longitude)^2
     LIMIT 1
    ) AS nodeID,
    c.name,
    CASE
        -- Restrooms
        WHEN c.name ILIKE '%bathroom%' OR c.name ILIKE '%restroom%'
            THEN 'restroom'
        -- Gates (D followed by digits)
        WHEN c.name ~ '^D\d+$'
            THEN 'gate'
        -- Elevators
        WHEN c.name ILIKE '%elevator%'
            THEN 'elevator'
        -- Escalators
        WHEN c.name ILIKE '%escalator%'
            THEN 'escalator'
        -- Lactation
        WHEN c.name ILIKE '%lactation%'
            THEN 'lactation_room'
        -- Information
        WHEN c.name ILIKE '%information%' OR c.name ILIKE '%info%kiosk%'
            THEN 'information'
        -- Chapel
        WHEN c.name ILIKE '%chapel%' OR c.name ILIKE '%interfaith%'
            THEN 'chapel'
        -- Children / play
        WHEN c.name ILIKE '%children%' OR c.name ILIKE '%play area%'
            THEN 'children_area'
        -- TSA
        WHEN c.name ILIKE '%tsa%'
            THEN 'tsa'
        -- Lounges
        WHEN c.name ILIKE '%lounge%' OR c.name ILIKE '%admirals club%'
             OR c.name ILIKE '%centurion%'
            THEN 'lounge'
        -- ATM / Credit Union
        WHEN c.name ILIKE '%atm%' OR c.name ILIKE '%credit union%'
            THEN 'atm'
        -- Currency exchange
        WHEN c.name ILIKE '%currency%' OR c.name ILIKE '%exchange%'
            THEN 'currency_exchange'
        -- Duty free
        WHEN c.name ILIKE '%duty free%'
            THEN 'shop'
        -- Minute Suites / Be Relax
        WHEN c.name ILIKE '%minute suite%' OR c.name ILIKE '%be relax%'
            THEN 'rest'
        -- Shops / retail
        WHEN c.name ILIKE ANY(ARRAY[
            '%lego%', '%coach%', '%longchamp%', '%montblanc%', '%chanel%',
            '%occitane%', '%jo malone%', '%m·a·c%', '%istore%', '%relay%',
            '%360 west%', '%world news%', '%wall street%', '%travel+%',
            '%news%gifts%', '%essentials%', '%sugarphoria%', '%coca-cola%'
        ])
            THEN 'shop'
        -- Food & drink (broad catch-all)
        WHEN c.name ILIKE ANY(ARRAY[
            '%grill%', '%bar%', '%kitchen%', '%coffee%', '%starbucks%',
            '%mcdonald%', '%chick-fil%', '%whataburger%', '%subway%',
            '%chili%', '%buffalo%', '%barbecue%', '%dickey%', '%cake%',
            '%banh%', '%eatzi%', '%trinity%', '%lavazza%', '%brewed%',
            '%peach cobbler%', '%flying saucer%', '%applebee%', '%hickory%',
            '%tx/mx%', '%italian kitchen%', '%wolfgang%', '%cru%',
            '%7-eleven%'
        ])
            THEN 'food'
        ELSE 'amenity'
    END AS type,
    c.latitude,
    c.longitude
FROM csv_import c
WHERE c.latitude IS NOT NULL AND c.longitude IS NOT NULL;

-- Step 4: Clean up
DROP TABLE csv_import;

-- Step 5: Verify
SELECT type, COUNT(*) AS count
FROM amenities
GROUP BY type
ORDER BY count DESC;
