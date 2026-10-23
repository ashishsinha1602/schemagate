WITH s AS (
  SELECT name, version, step,
         MAX(CASE WHEN model = 'Stack' THEN test_score END) AS stack_score,
         MAX(CASE WHEN model <> 'Stack' THEN test_score END) AS max_other
  FROM model_score
  GROUP BY name, version, step
),
st AS (
  SELECT m.L1_model,
         CASE WHEN s.max_other < s.stack_score THEN 'strong'
              WHEN s.max_other = s.stack_score THEN 'soft'
         END AS status
  FROM s
  JOIN model m ON m.name = s.name AND m.version = s.version AND m.step = s.step
  WHERE s.max_other <= s.stack_score
),
c AS (
  SELECT status, L1_model, COUNT(*) AS cnt
  FROM st
  GROUP BY status, L1_model
),
r AS (
  SELECT status, L1_model, cnt,
         RANK() OVER (PARTITION BY status ORDER BY cnt DESC) AS rk
  FROM c
)
SELECT status, L1_model, cnt
FROM r
WHERE rk = 1