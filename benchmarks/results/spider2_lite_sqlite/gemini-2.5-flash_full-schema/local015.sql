WITH
  helmet_used_collisions AS (
    SELECT DISTINCT
      T1.case_id
    FROM main.collisions AS T1
    INNER JOIN main.parties AS T2
      ON T1.case_id = T2.case_id
    WHERE
      T1.motorcycle_collision = 1 AND (
        T2.party_safety_equipment_1 IN ('driver, motorcycle helmet used', 'passenger, motorcycle helmet used') OR
        T2.party_safety_equipment_2 IN ('driver, motorcycle helmet used', 'passenger, motorcycle helmet used')
      )
  ),
  helmet_not_used_collisions AS (
    SELECT DISTINCT
      T1.case_id
    FROM main.collisions AS T1
    INNER JOIN main.parties AS T2
      ON T1.case_id = T2.case_id
    WHERE
      T1.motorcycle_collision = 1 AND (
        T2.party_safety_equipment_1 IN ('driver, motorcycle helmet not used', 'passenger, motorcycle helmet not used') OR
        T2.party_safety_equipment_2 IN ('driver, motorcycle helmet not used', 'passenger, motorcycle helmet not used')
      )
  ),
  helmet_used_stats AS (
    SELECT
      SUM(T1.motorcyclist_killed_count) AS total_killed,
      COUNT(DISTINCT T1.case_id) AS total_collisions
    FROM main.collisions AS T1
    WHERE
      T1.case_id IN (
        SELECT
          case_id
        FROM helmet_used_collisions
      )
  ),
  helmet_not_used_stats AS (
    SELECT
      SUM(T1.motorcyclist_killed_count) AS total_killed,
      COUNT(DISTINCT T1.case_id) AS total_collisions
    FROM main.collisions AS T1
    WHERE
      T1.case_id IN (
        SELECT
          case_id
        FROM helmet_not_used_collisions
      )
  )
SELECT
  CAST(hus.total_killed AS REAL) * 100.0 / hus.total_collisions AS helmet_used_fatality_rate,
  CAST(hnus.total_killed AS REAL) * 100.0 / hnus.total_collisions AS helmet_not_used_fatality_rate
FROM helmet_used_stats AS hus, helmet_not_used_stats AS hnus