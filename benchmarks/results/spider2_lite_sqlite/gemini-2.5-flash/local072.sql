WITH TargetCountry AS (
    SELECT
        country_code_2
    FROM
        main.cities
    WHERE
        STRFTIME('%Y-%m', insert_date) = '2022-01'
    GROUP BY
        country_code_2
    HAVING
        COUNT(DISTINCT STRFTIME('%Y-%m-%d', insert_date)) = 9
),
CountryJanuaryDistinctDays AS (
    SELECT DISTINCT
        STRFTIME('%Y-%m-%d', insert_date) AS insert_day
    FROM
        main.cities
    WHERE
        country_code_2 = (SELECT country_code_2 FROM TargetCountry)
        AND STRFTIME('%Y-%m', insert_date) = '2022-01'
    ORDER BY
        insert_day
),
ConsecutiveGroups AS (
    SELECT
        insert_day,
        JULIANDAY(insert_day) - ROW_NUMBER() OVER (ORDER BY insert_day) AS grp
    FROM
        CountryJanuaryDistinctDays
),
LongestConsecutivePeriod AS (
    SELECT
        MIN(insert_day) AS period_start,
        MAX(insert_day) AS period_end
    FROM
        ConsecutiveGroups
    GROUP BY
        grp
    ORDER BY
        COUNT(insert_day) DESC, MIN(insert_day) ASC
    LIMIT 1
),
DataInLongestPeriod AS (
    SELECT
        c.city_id,
        c.capital
    FROM
        main.cities AS c
    WHERE
        c.country_code_2 = (SELECT country_code_2 FROM TargetCountry)
        AND STRFTIME('%Y-%m-%d', c.insert_date) BETWEEN (SELECT period_start FROM LongestConsecutivePeriod) AND (SELECT period_end FROM LongestConsecutivePeriod)
)
SELECT
    CAST(SUM(CASE WHEN capital = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(city_id)
FROM
    DataInLongestPeriod