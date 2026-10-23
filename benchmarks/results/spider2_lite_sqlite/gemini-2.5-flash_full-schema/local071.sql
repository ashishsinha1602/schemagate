WITH June2022Cities AS (
    SELECT DISTINCT
        country_code_2,
        insert_date
    FROM
        main.cities
    WHERE
        insert_date LIKE '2022-06-%'
),
RankedDates AS (
    SELECT
        country_code_2,
        insert_date,
        julianday(insert_date) - ROW_NUMBER() OVER (PARTITION BY country_code_2 ORDER BY insert_date) AS consecutive_group_id
    FROM
        June2022Cities
),
Streaks AS (
    SELECT
        country_code_2,
        consecutive_group_id,
        COUNT(insert_date) AS streak_length
    FROM
        RankedDates
    GROUP BY
        country_code_2,
        consecutive_group_id
),
MaxStreakPerCountry AS (
    SELECT
        country_code_2,
        MAX(streak_length) AS max_streak
    FROM
        Streaks
    GROUP BY
        country_code_2
),
OverallMaxStreak AS (
    SELECT
        MAX(max_streak) AS overall_max_streak
    FROM
        MaxStreakPerCountry
)
SELECT
    T1.country_code_2
FROM
    MaxStreakPerCountry AS T1
JOIN
    OverallMaxStreak AS T2
ON
    T1.max_streak = T2.overall_max_streak