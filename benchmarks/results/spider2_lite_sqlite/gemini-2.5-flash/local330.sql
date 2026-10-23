WITH SessionPages AS (
    SELECT
        session,
        path,
        stamp,
        ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp ASC) AS rn_asc,
        ROW_NUMBER() OVER (PARTITION BY session ORDER BY stamp DESC) AS rn_desc
    FROM
        main.activity_log
),
LandingExitPages AS (
    SELECT
        session,
        path
    FROM
        SessionPages
    WHERE
        rn_asc = 1 OR rn_desc = 1
)
SELECT
    SUM(session_count)
FROM (
    SELECT
        path,
        COUNT(DISTINCT session) AS session_count
    FROM
        LandingExitPages
    GROUP BY
        path
)