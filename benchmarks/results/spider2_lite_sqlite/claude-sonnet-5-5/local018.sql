WITH c AS (
  SELECT ci.db_year AS y, co.pcf_violation_category AS cat
  FROM collisions co
  JOIN case_ids ci ON ci.case_id = co.case_id
  WHERE ci.db_year IN (2011, 2021)
),
tot AS (
  SELECT y, COUNT(*) AS n FROM c GROUP BY y
),
top AS (
  SELECT cat FROM c
  WHERE y = 2021 AND cat IS NOT NULL
  GROUP BY cat
  ORDER BY COUNT(*) DESC
  LIMIT 1
)
SELECT top.cat AS pcf_violation_category,
  100.0 * (SELECT COUNT(*) FROM c WHERE c.y = 2011 AND c.cat = top.cat) / (SELECT n FROM tot WHERE y = 2011)
  - 100.0 * (SELECT COUNT(*) FROM c WHERE c.y = 2021 AND c.cat = top.cat) / (SELECT n FROM tot WHERE y = 2021) AS percentage_point_decrease
FROM top