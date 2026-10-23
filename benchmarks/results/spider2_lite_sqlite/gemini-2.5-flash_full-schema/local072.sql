WITH TargetCountry AS (
    -- Step 1: Identify the country with data inserted on nine different days in January 2022
    SELECT country_code_2
    FROM main.cities
    WHERE STRFTIME('%Y-%m', insert_date) = '2022-01'
    GROUP BY country_code_2
    HAVING COUNT(DISTINCT insert_date) = 9
),
CountryDistinctDates AS (
    -- Get all distinct insertion dates for the identified country in January 2022
    SELECT DISTINCT
        c.insert_date,
        c.country_code_2
    FROM
        main.cities c
    JOIN
        TargetCountry tc ON c.country_code_2 = tc.country_code_2
    WHERE
        STRFTIME('%Y-%m', c.insert_date) = '2022-01'
),
DateGroups AS (
    -- Group consecutive dates for the identified country
    SELECT
        insert_date,
        country_code_2,
        JULIANDAY(insert_date) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY insert_date) AS date_group_id
    FROM
        CountryDistinctDates
),
LongestConsecutivePeriod AS (
    -- Step 2: Find the longest consecutive period of data insertions for this country during January 2022
    SELECT
        country_code_2,
        MIN(insert_date) AS period_start_date,
        MAX(insert_date) AS period_end_date,
        COUNT(insert_date) AS period_length_days
    FROM
        DateGroups
    GROUP BY
        country_code_2, date_group_id
    ORDER BY
        period_length_days DESC, period_start_date ASC
    LIMIT 1
)
-- Step 3: Calculate the proportion of entries that are from its capital city within this longest consecutive insertion period
SELECT
    CAST(SUM(CASE WHEN c.capital = 1 THEN 1 ELSE 0 END) AS REAL) / COUNT(c.city_id) AS capital_proportion
FROM
    main.cities c
JOIN
    LongestConsecutivePeriod lcp ON c.country_code_2 = lcp.country_code_2
WHERE
    c.insert_date BETWEEN lcp.period_start_date AND lcp.period_end_date