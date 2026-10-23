WITH Unicorns2019_2021 AS (
    SELECT
        cf.company_id,
        CAST(SUBSTR(cd.date_joined, 1, 4) AS INTEGER) AS join_year,
        ci.industry
    FROM
        main.companies_funding AS cf
    JOIN
        main.companies_dates AS cd
        ON cf.company_id = cd.company_id
    JOIN
        main.companies_industries AS ci
        ON cf.company_id = ci.company_id
    WHERE
        cf.valuation >= 1000000000
        AND CAST(SUBSTR(cd.date_joined, 1, 4) AS INTEGER) BETWEEN 2019 AND 2021
),
TopIndustry AS (
    SELECT
        industry
    FROM
        Unicorns2019_2021
    GROUP BY
        industry
    ORDER BY
        COUNT(company_id) DESC
    LIMIT 1
),
YearlyUnicornCounts AS (
    SELECT
        u.join_year,
        COUNT(u.company_id) AS num_unicorns
    FROM
        Unicorns2019_2021 AS u
    JOIN
        TopIndustry AS ti
        ON u.industry = ti.industry
    GROUP BY
        u.join_year
)
SELECT
    AVG(COALESCE(yuc.num_unicorns, 0))
FROM (
    SELECT 2019 AS year
    UNION ALL
    SELECT 2020
    UNION ALL
    SELECT 2021
) AS years_range
LEFT JOIN
    YearlyUnicornCounts AS yuc
    ON years_range.year = yuc.join_year