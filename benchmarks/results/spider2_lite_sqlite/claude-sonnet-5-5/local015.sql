WITH helmet AS (
  SELECT DISTINCT case_id FROM parties
  WHERE party_safety_equipment_1 IN ('driver, motorcycle helmet used','passenger, motorcycle helmet used')
     OR party_safety_equipment_2 IN ('driver, motorcycle helmet used','passenger, motorcycle helmet used')
),
nohelmet AS (
  SELECT DISTINCT case_id FROM parties
  WHERE party_safety_equipment_1 IN ('driver, motorcycle helmet not used','passenger, motorcycle helmet not used')
     OR party_safety_equipment_2 IN ('driver, motorcycle helmet not used','passenger, motorcycle helmet not used')
)
SELECT
  (SELECT 100.0 * SUM(c.motorcyclist_killed_count) / COUNT(*)
   FROM collisions c
   WHERE c.motorcycle_collision = 1 AND c.case_id IN (SELECT case_id FROM helmet)) AS helmet_fatality_pct,
  (SELECT 100.0 * SUM(c.motorcyclist_killed_count) / COUNT(*)
   FROM collisions c
   WHERE c.motorcycle_collision = 1 AND c.case_id IN (SELECT case_id FROM nohelmet)) AS no_helmet_fatality_pct