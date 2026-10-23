WITH top_states AS (
  SELECT state,
         COUNT(*) AS total,
         SUM(CASE WHEN aggressive = 0 THEN 1 ELSE 0 END) AS friendly,
         SUM(CASE WHEN aggressive = 1 THEN 1 ELSE 0 END) AS hostile,
         AVG(age) AS avg_age
  FROM alien_data
  GROUP BY state
  ORDER BY COUNT(*) DESC
  LIMIT 10
)
SELECT COUNT(*) AS num_states
FROM top_states
WHERE friendly * 1.0 / total > hostile * 1.0 / total
  AND avg_age > 200