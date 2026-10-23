WITH d AS (
  SELECT r.year AS year, res.driver_id, SUM(res.points) AS pts
  FROM results res
  JOIN races r ON r.race_id = res.race_id
  GROUP BY r.year, res.driver_id
),
dm AS (
  SELECT year, MAX(pts) AS max_driver FROM d GROUP BY year
),
c AS (
  SELECT r.year AS year, res.constructor_id, SUM(res.points) AS pts
  FROM results res
  JOIN races r ON r.race_id = res.race_id
  GROUP BY r.year, res.constructor_id
),
cm AS (
  SELECT year, MAX(pts) AS max_constructor FROM c GROUP BY year
)
SELECT dm.year, dm.max_driver + cm.max_constructor AS total
FROM dm
JOIN cm ON cm.year = dm.year
ORDER BY total ASC, dm.year ASC
LIMIT 3