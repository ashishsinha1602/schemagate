WITH step_scores AS (
    SELECT name, version, step,
           MAX(CASE WHEN model <> 'Stack' THEN test_score END) AS max_other,
           MAX(CASE WHEN model = 'Stack' THEN test_score END) AS stack_score
    FROM main.model_score
    GROUP BY name, version, step
),
step_status AS (
    SELECT name, version, step,
           CASE WHEN max_other < stack_score THEN 'strong'
                WHEN max_other = stack_score THEN 'soft'
           END AS status
    FROM step_scores
),
counts AS (
    SELECT s.status, m.L1_model, COUNT(*) AS cnt
    FROM step_status s
    JOIN main.model m
      ON m.name = s.name AND m.version = s.version AND m.step = s.step
    WHERE s.status IS NOT NULL
    GROUP BY s.status, m.L1_model
),
ranked AS (
    SELECT status, L1_model, cnt,
           RANK() OVER (PARTITION BY status ORDER BY cnt DESC) AS rnk
    FROM counts
)
SELECT status, L1_model, cnt AS occurrences
FROM ranked
WHERE rnk = 1
ORDER BY status