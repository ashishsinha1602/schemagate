WITH cleaned AS (
    SELECT
        CompanyName,
        Location,
        CAST(
            REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
                TRIM(Salary), '₹', ''), ',', ''), '/yr', ''), '/mo', ''), '/hr', ''), ' ', ''), '$', '')
            AS REAL
        ) AS salary_num
    FROM SalaryDataset
    WHERE Salary IS NOT NULL
),
national AS (
    SELECT AVG(salary_num) AS avg_country
    FROM cleaned
),
company_city AS (
    SELECT
        Location,
        CompanyName,
        AVG(salary_num) AS avg_state
    FROM cleaned
    WHERE Location IN ('Mumbai', 'Pune', 'New Delhi', 'Hyderabad')
    GROUP BY Location, CompanyName
),
ranked AS (
    SELECT
        Location,
        CompanyName,
        avg_state,
        ROW_NUMBER() OVER (PARTITION BY Location ORDER BY avg_state DESC) AS rn
    FROM company_city
)
SELECT
    r.Location AS "Location",
    r.CompanyName AS "Company Name",
    ROUND(r.avg_state, 2) AS "Average Salary in State",
    ROUND(n.avg_country, 2) AS "Average Salary in Country"
FROM ranked r
CROSS JOIN national n
WHERE r.rn <= 5
ORDER BY r.Location, r.rn