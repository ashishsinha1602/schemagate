WITH CollisionsByYear AS (
    SELECT
        ci.db_year,
        c.pcf_violation_category
    FROM
        main.collisions AS c
    JOIN
        main.case_ids AS ci
        ON c.case_id = ci.case_id
    WHERE
        ci.db_year IN (2011, 2021)
),
MostCommonCategory2021 AS (
    SELECT
        pcf_violation_category
    FROM
        CollisionsByYear
    WHERE
        db_year = 2021
    GROUP BY
        pcf_violation_category
    ORDER BY
        COUNT(*) DESC
    LIMIT 1
),
Calculations AS (
    SELECT
        (SELECT pcf_violation_category FROM MostCommonCategory2021) AS target_category,
        SUM(CASE WHEN db_year = 2021 THEN 1 ELSE 0 END) AS total_collisions_2021,
        SUM(CASE WHEN db_year = 2011 THEN 1 ELSE 0 END) AS total_collisions_2011,
        SUM(CASE WHEN db_year = 2021 AND pcf_violation_category = (SELECT pcf_violation_category FROM MostCommonCategory2021) THEN 1 ELSE 0 END) AS category_collisions_2021,
        SUM(CASE WHEN db_year = 2011 AND pcf_violation_category = (SELECT pcf_violation_category FROM MostCommonCategory2021) THEN 1 ELSE 0 END) AS category_collisions_2011
    FROM
        CollisionsByYear
)
SELECT
    CAST(c.category_collisions_2011 AS REAL) * 100.0 / c.total_collisions_2011 -
    CAST(c.category_collisions_2021 AS REAL) * 100.0 / c.total_collisions_2021
FROM
    Calculations AS c