WITH June2022Cities AS (
    SELECT DISTINCT
        country_code_2,
        insert_date
    FROM
        main.cities
    WHERE
        strftime('%Y-%m', insert_date) = '2022-06'
),
RankedDates AS (
    SELECT
        country_code_2,
        insert_date,
        strftime('%J', insert_date) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY insert_date) AS streak_group
    FROM
        June2022Cities
),
StreakLengths AS (
    SELECT
        country_code_2,
        COUNT(insert_date) AS streak_length
    FROM
        RankedDates
    GROUP BY
        country_code_2,
        streak_group
),
MaxStreak AS (
    SELECT
        MAX(streak_length) AS max_len
    FROM
        StreakLengths
)
SELECT DISTINCT
    sl.country_code_2
FROM
    StreakLengths sl, MaxStreak ms
WHERE
    sl.streak_length = ms.max_len