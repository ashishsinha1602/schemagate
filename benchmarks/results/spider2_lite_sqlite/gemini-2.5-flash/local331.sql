WITH RankedActivity AS (
    SELECT
        session,
        stamp,
        path,
        LEAD(path, 1) OVER (PARTITION BY session ORDER BY stamp) AS next_path,
        LEAD(path, 2) OVER (PARTITION BY session ORDER BY stamp) AS third_path
    FROM
        main.activity_log
)
SELECT
    third_path,
    COUNT(*) AS visit_count
FROM
    RankedActivity
WHERE
    path = '/detail'
    AND next_path = '/detail'
    AND third_path IS NOT NULL
GROUP BY
    third_path
ORDER BY
    visit_count DESC
LIMIT 3