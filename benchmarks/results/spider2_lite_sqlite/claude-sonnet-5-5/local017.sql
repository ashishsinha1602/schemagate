WITH counts AS (
  SELECT ci.db_year AS db_year, c.pcf_violation_category AS cause, COUNT(*) AS n
  FROM collisions c
  JOIN case_ids ci ON ci.case_id = c.case_id
  WHERE c.pcf_violation_category IS NOT NULL
  GROUP BY ci.db_year, c.pcf_violation_category
),
ranked AS (
  SELECT db_year, cause, ROW_NUMBER() OVER (PARTITION BY db_year ORDER BY n DESC, cause) AS rn
  FROM counts
),
top2 AS (
  SELECT db_year, group_concat(cause, '|') AS combo
  FROM (
    SELECT db_year, cause
    FROM ranked
    WHERE rn <= 2
    ORDER BY db_year, cause
  )
  GROUP BY db_year
)
SELECT db_year
FROM top2
WHERE combo IN (SELECT combo FROM top2 GROUP BY combo HAVING COUNT(*) = 1)