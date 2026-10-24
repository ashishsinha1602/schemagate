WITH dr AS (
  SELECT r.driver_id, ra.year, ra.round, MAX(r.constructor_id) AS cid
  FROM results r
  JOIN races ra ON ra.race_id = r.race_id
  GROUP BY r.driver_id, ra.year, ra.round
),
dy AS (
  SELECT DISTINCT driver_id, year FROM dr
),
grid AS (
  SELECT dy.driver_id, dy.year, ra.round, d.cid
  FROM dy
  JOIN races ra ON ra.year = dy.year
  LEFT JOIN dr d
    ON d.driver_id = dy.driver_id AND d.year = dy.year AND d.round = ra.round
),
g2 AS (
  SELECT driver_id, year, round, cid,
    SUM(CASE WHEN cid IS NULL THEN 1 ELSE 0 END)
      OVER (PARTITION BY driver_id, year) AS miss_cnt,
    MAX(CASE WHEN cid IS NOT NULL THEN round END)
      OVER (PARTITION BY driver_id, year ORDER BY round
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS prev_r,
    MIN(CASE WHEN cid IS NOT NULL THEN round END)
      OVER (PARTITION BY driver_id, year ORDER BY round
            ROWS BETWEEN 1 FOLLOWING AND UNBOUNDED FOLLOWING) AS next_r
  FROM grid
),
blocks AS (
  SELECT driver_id, year, prev_r, next_r,
         MIN(round) AS first_round, MAX(round) AS last_round
  FROM g2
  WHERE cid IS NULL AND miss_cnt < 3
    AND prev_r IS NOT NULL AND next_r IS NOT NULL
  GROUP BY driver_id, year, prev_r, next_r
),
bc AS (
  SELECT b.first_round, b.last_round,
         p.cid AS before_cid, n.cid AS after_cid
  FROM blocks b
  JOIN dr p ON p.driver_id = b.driver_id AND p.year = b.year AND p.round = b.prev_r
  JOIN dr n ON n.driver_id = b.driver_id AND n.year = b.year AND n.round = b.next_r
)
SELECT AVG(first_round) AS avg_first_round,
       AVG(last_round) AS avg_last_round
FROM bc
WHERE before_cid <> after_cid