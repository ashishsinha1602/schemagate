WITH season_drives AS (
  SELECT
    dv.year,
    dv.driver_id,
    MAX(CASE WHEN dv.is_first_drive_of_season = 1 THEN dv.constructor_id END) AS first_constructor_id,
    MAX(CASE WHEN dv.is_final_drive_of_season = 1 THEN dv.constructor_id END) AS last_constructor_id,
    MIN(dv.first_round) AS min_round,
    MAX(dv.last_round) AS max_round
  FROM drives dv
  WHERE dv.year BETWEEN 1950 AND 1959
  GROUP BY dv.year, dv.driver_id
)
SELECT DISTINCT d.driver_id, d.full_name
FROM season_drives s
JOIN drivers d ON d.driver_id = s.driver_id
WHERE s.first_constructor_id = s.last_constructor_id
  AND s.max_round > s.min_round
ORDER BY d.full_name