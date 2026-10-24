WITH per_collision AS (
  SELECT
    c.case_id,
    MAX(COALESCE(c.motorcyclist_killed_count, 0)) AS killed,
    MAX(CASE WHEN p.party_safety_equipment_1 IN ('driver, motorcycle helmet used', 'passenger, motorcycle helmet used')
              OR p.party_safety_equipment_2 IN ('driver, motorcycle helmet used', 'passenger, motorcycle helmet used')
             THEN 1 ELSE 0 END) AS helmet_used,
    MAX(CASE WHEN p.party_safety_equipment_1 IN ('driver, motorcycle helmet not used', 'passenger, motorcycle helmet not used')
              OR p.party_safety_equipment_2 IN ('driver, motorcycle helmet not used', 'passenger, motorcycle helmet not used')
             THEN 1 ELSE 0 END) AS helmet_not_used
  FROM collisions c
  JOIN parties p ON p.case_id = c.case_id
  WHERE c.motorcycle_collision = 1
  GROUP BY c.case_id
)
SELECT
  100.0 * SUM(CASE WHEN helmet_used = 1 THEN killed ELSE 0 END) / NULLIF(SUM(helmet_used), 0) AS helmet_used_fatality_pct,
  100.0 * SUM(CASE WHEN helmet_not_used = 1 THEN killed ELSE 0 END) / NULLIF(SUM(helmet_not_used), 0) AS helmet_not_used_fatality_pct
FROM per_collision