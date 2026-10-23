WITH q AS (
  SELECT name, version, step
  FROM model_score
  WHERE step IN (1, 2, 3)
  GROUP BY name, version, step
  HAVING MAX(CASE WHEN model <> 'Stack' THEN test_score END) < MAX(CASE WHEN model = 'Stack' THEN test_score END)
)
SELECT p.name
FROM problem p
WHERE (SELECT COUNT(*) FROM q WHERE q.name = p.name) > (SELECT COUNT(*) FROM solution s WHERE s.name = p.name)