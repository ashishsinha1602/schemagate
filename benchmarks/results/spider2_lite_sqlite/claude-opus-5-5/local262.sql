WITH per_step AS (
  SELECT ms.name, ms.version, ms.step,
         MAX(CASE WHEN ms.model <> 'Stack' THEN ms.test_score END) AS max_other,
         MAX(CASE WHEN ms.model = 'Stack' THEN ms.test_score END) AS stack_score
  FROM model_score ms
  WHERE ms.step IN (1, 2, 3)
  GROUP BY ms.name, ms.version, ms.step
),
stack_wins AS (
  SELECT name, COUNT(*) AS win_count
  FROM per_step
  WHERE max_other < stack_score
  GROUP BY name
),
sol_counts AS (
  SELECT name, COUNT(*) AS sol_count
  FROM solution
  GROUP BY name
)
SELECT w.name
FROM stack_wins w
LEFT JOIN sol_counts s ON s.name = w.name
WHERE w.win_count > COALESCE(s.sol_count, 0)