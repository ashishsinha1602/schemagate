WITH StepScores AS (
    SELECT
        ms.name,
        ms.version,
        ms.step,
        MAX(CASE WHEN ms.model = 'Stack' THEN ms.test_score ELSE NULL END) AS stack_test_score,
        MAX(CASE WHEN ms.model != 'Stack' THEN ms.test_score ELSE NULL END) AS max_non_stack_test_score
    FROM main.model_score AS ms
    GROUP BY ms.name, ms.version, ms.step
),
ModelStatus AS (
    SELECT
        ss.name,
        ss.version,
        MAX(CASE WHEN ss.stack_test_score IS NOT NULL AND ss.max_non_stack_test_score IS NOT NULL AND ss.max_non_stack_test_score < ss.stack_test_score THEN 1 ELSE 0 END) AS is_strong,
        MAX(CASE WHEN ss.stack_test_score IS NOT NULL AND ss.max_non_stack_test_score IS NOT NULL AND ss.max_non_stack_test_score = ss.stack_test_score THEN 1 ELSE 0 END) AS is_soft
    FROM StepScores AS ss
    GROUP BY ss.name, ss.version
),
L1ModelStatus AS (
    SELECT
        se.L1_model,
        ms.is_strong,
        ms.is_soft
    FROM ModelStatus AS ms
    JOIN main.solution_ext AS se
        ON ms.name = se.name AND ms.version = se.version
),
L1ModelCounts AS (
    SELECT
        L1_model,
        SUM(is_strong) AS strong_count,
        SUM(is_soft) AS soft_count
    FROM L1ModelStatus
    GROUP BY L1_model
)
SELECT
    'strong' AS status_type,
    L1_model,
    strong_count AS occurrence_count
FROM L1ModelCounts
WHERE strong_count = (SELECT MAX(strong_count) FROM L1ModelCounts) AND strong_count > 0
UNION ALL
SELECT
    'soft' AS status_type,
    L1_model,
    soft_count AS occurrence_count
FROM L1ModelCounts
WHERE soft_count = (SELECT MAX(soft_count) FROM L1ModelCounts) AND soft_count > 0