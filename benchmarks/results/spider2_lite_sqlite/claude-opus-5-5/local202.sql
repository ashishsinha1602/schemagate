WITH s AS (
  SELECT state,
         COUNT(*) AS pop,
         SUM(CASE WHEN aggressive = 0 THEN 1 ELSE 0 END) AS friendly,
         SUM(CASE WHEN aggressive = 1 THEN 1 ELSE 0 END) AS hostile,
         AVG(age) AS avg_age
  FROM alien_data
  GROUP BY state
),
top10 AS (
  SELECT * FROM s ORDER BY pop DESC LIMIT 10
)
SELECT COUNT(*) AS num_states
FROM top10
WHERE friendly > hostile AND avg_age > 200