WITH StateAlienStats AS (
  SELECT
    state,
    COUNT(id) AS total_aliens,
    SUM(CASE WHEN aggressive = 0 THEN 1 ELSE 0 END) AS friendly_aliens,
    SUM(CASE WHEN aggressive = 1 THEN 1 ELSE 0 END) AS hostile_aliens,
    AVG(age) AS average_age
  FROM main.alien_data
  GROUP BY
    state
), Top10States AS (
  SELECT
    state,
    total_aliens,
    friendly_aliens,
    hostile_aliens,
    average_age
  FROM StateAlienStats
  ORDER BY
    total_aliens DESC
  LIMIT 10
)
SELECT
  COUNT(state)
FROM Top10States
WHERE
  friendly_aliens > hostile_aliens AND average_age > 200