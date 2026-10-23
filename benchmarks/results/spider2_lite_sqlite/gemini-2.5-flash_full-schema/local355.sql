WITH DriverRaceInfo AS (
    SELECT
        r.year,
        r.round,
        res.driver_id,
        res.constructor_id,
        LAG(r.round) OVER (PARTITION BY r.year, res.driver_id ORDER BY r.round) AS prev_round_participated,
        LAG(res.constructor_id) OVER (PARTITION BY r.year, res.driver_id ORDER BY r.round) AS prev_constructor_participated
    FROM
        main.results AS res
    JOIN
        main.races AS r ON res.race_id = r.race_id
),
FilteredHiatuses AS (
    SELECT
        year,
        driver_id,
        prev_round_participated + 1 AS first_missed_round,
        round - 1 AS last_missed_round,
        (round - 1) - (prev_round_participated + 1) + 1 AS num_missed_races,
        prev_constructor_participated,
        constructor_id AS next_constructor_participated
    FROM
        DriverRaceInfo
    WHERE
        prev_round_participated IS NOT NULL
        AND round - prev_round_participated > 1
        AND (round - 1) - (prev_round_participated + 1) + 1 < 3
        AND prev_constructor_participated <> constructor_id
)
SELECT
    AVG(first_missed_round),
    AVG(last_missed_round)
FROM
    FilteredHiatuses