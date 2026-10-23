WITH ChineseCitiesJuly2021Dates AS (
    SELECT DISTINCT
        insert_date AS date_val
    FROM
        main.cities
    WHERE
        country_code_2 = 'cn'
        AND insert_date BETWEEN '2021-07-01' AND '2021-07-31'
),
RankedDates AS (
    SELECT
        date_val,
        ROW_NUMBER() OVER (ORDER BY date_val) AS rn,
        JULIANDAY(date_val) AS julian_day
    FROM
        ChineseCitiesJuly2021Dates
),
StreaksGrouped AS (
    SELECT
        date_val,
        julian_day - rn AS streak_group
    FROM
        RankedDates
),
StreakLengths AS (
    SELECT
        streak_group,
        COUNT(*) AS streak_length
    FROM
        StreaksGrouped
    GROUP BY
        streak_group
),
MinMaxLengths AS (
    SELECT
        MIN(streak_length) AS min_len,
        MAX(streak_length) AS max_len
    FROM
        StreakLengths
),
TargetDates AS (
    SELECT
        sg.date_val
    FROM
        StreaksGrouped AS sg
    JOIN
        StreakLengths AS sl ON sg.streak_group = sl.streak_group
    JOIN
        MinMaxLengths AS mml ON sl.streak_length = mml.min_len OR sl.streak_length = mml.max_len
)
SELECT
    td.date_val AS date,
    UPPER(SUBSTR(c.city_name, 1, 1)) || LOWER(SUBSTR(c.city_name, 2)) AS city_name
FROM
    TargetDates AS td
JOIN
    main.cities AS c ON td.date_val = c.insert_date
WHERE
    c.country_code_2 = 'cn'
GROUP BY
    td.date_val
ORDER BY
    td.date_val