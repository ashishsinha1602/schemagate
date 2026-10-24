WITH counts AS (
  SELECT ci.db_year AS yr, c.primary_collision_factor AS factor, COUNT(*) AS n
  FROM collisions c
  JOIN case_ids ci ON c.case_id = ci.case_id
  WHERE c.primary_collision_factor IS NOT NULL
  GROUP BY ci.db_year, c.primary_collision_factor
),
ranked AS (
  SELECT yr, factor, ROW_NUMBER() OVER (PARTITION BY yr ORDER BY n DESC, factor) AS rn
  FROM counts
),
top2 AS (
  SELECT yr, MIN(factor) || ' | ' || MAX(factor) AS combo
  FROM ranked
  WHERE rn <= 2
  GROUP BY yr
),
combo_freq AS (
  SELECT combo, COUNT(*) AS cnt
  FROM top2
  GROUP BY combo
)
SELECT yr, combo
FROM top2
WHERE combo <> (SELECT combo FROM combo_freq ORDER BY cnt DESC LIMIT 1)