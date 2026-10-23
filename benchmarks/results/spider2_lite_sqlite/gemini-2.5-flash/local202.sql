WITH state_alien_stats AS (
  SELECT
    state,
    COUNT(id) AS total_aliens,
    SUM(CASE WHEN aggressive = 0 THEN 1 ELSE 0 END) AS friendly_aliens,
    SUM(CASE WHEN aggressive = 1 THEN 1 ELSE 0 END) AS hostile_aliens,
    AVG(age) AS average_age
  FROM main.alien_data
  GROUP BY
    state
), top_10_states AS (
  SELECT
    state,
    total_aliens,
    friendly_aliens,
    hostile_aliens,
    average_age,
    RANK() OVER (ORDER BY total_aliens DESC) AS rank_num
  FROM state_alien_stats
)
SELECT
  COUNT(state)
FROM top_10_states
WHERE
  rank_num <= 10 AND friendly_aliens > hostile_aliens AND average_age > 200