WITH stack_scores AS (
    SELECT
        name,
        version,
        step,
        test_score AS stack_test_score
    FROM
        main.model_score
    WHERE
        model = 'Stack' AND step IN (1, 2, 3)
), non_stack_max_scores AS (
    SELECT
        name,
        version,
        step,
        MAX(test_score) AS max_non_stack_test_score
    FROM
        main.model_score
    WHERE
        model != 'Stack' AND step IN (1, 2, 3)
    GROUP BY
        name,
        version,
        step
), qualified_steps AS (
    SELECT
        ss.name,
        ss.version,
        ss.step
    FROM
        stack_scores ss
    JOIN
        non_stack_max_scores nsms ON ss.name = nsms.name
                                   AND ss.version = nsms.version
                                   AND ss.step = nsms.step
    WHERE
        nsms.max_non_stack_test_score < ss.stack_test_score
), problem_qualified_count AS (
    SELECT
        name,
        COUNT(*) AS qualified_count
    FROM
        qualified_steps
    GROUP BY
        name
), problem_solution_count AS (
    SELECT
        name,
        COUNT(*) AS solution_count
    FROM
        main.solution
    GROUP BY
        name
)
SELECT
    pqc.name
FROM
    problem_qualified_count pqc
JOIN
    problem_solution_count psc ON pqc.name = psc.name
WHERE
    pqc.qualified_count > psc.solution_count