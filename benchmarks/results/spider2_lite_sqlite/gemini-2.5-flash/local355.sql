WITH driver_years AS (
    SELECT DISTINCT
        res.driver_id,
        r.year
    FROM main.results AS res
    JOIN main.races AS r
        ON res.race_id = r.race_id
),
all_races_for_driver_year AS (
    SELECT
        dy.driver_id,
        dy.year,
        ra.race_id,
        ra.round
    FROM driver_years AS dy
    JOIN main.races AS ra
        ON dy.year = ra.year
),
driver_race_status AS (
    SELECT
        ar.driver_id,
        ar.year,
        ar.race_id,
        ar.round,
        CASE WHEN res.driver_id IS NOT NULL THEN 1 ELSE 0 END AS participated,
        res.constructor_id
    FROM all_races_for_driver_year AS ar
    LEFT JOIN main.results AS res
        ON ar.race_id = res.race_id AND ar.driver_id = res.driver_id
),
hiatus_groups AS (
    SELECT
        driver_id,
        year,
        race_id,
        round,
        participated,
        constructor_id,
        round - ROW_NUMBER() OVER (PARTITION BY driver_id, year, participated ORDER BY round) AS group_id
    FROM driver_race_status
),
hiatus_summary AS (
    SELECT
        driver_id,
        year,
        group_id,
        MIN(round) AS first_missed_round,
        MAX(round) AS last_missed_round,
        COUNT(*) AS missed_races_count
    FROM hiatus_groups
    WHERE participated = 0
    GROUP BY driver_id, year, group_id
    HAVING COUNT(*) < 3
),
hiatus_with_surrounding_races AS (
    SELECT
        hs.driver_id,
        hs.year,
        hs.first_missed_round,
        hs.last_missed_round,
        hs.missed_races_count,
        (
            SELECT MAX(drs.round)
            FROM driver_race_status AS drs
            WHERE drs.driver_id = hs.driver_id
              AND drs.year = hs.year
              AND drs.round < hs.first_missed_round
              AND drs.participated = 1
        ) AS round_before_hiatus,
        (
            SELECT MIN(drs.round)
            FROM driver_race_status AS drs
            WHERE drs.driver_id = hs.driver_id
              AND drs.year = hs.year
              AND drs.round > hs.last_missed_round
              AND drs.participated = 1
        ) AS round_after_hiatus
    FROM hiatus_summary AS hs
),
hiatus_with_constructors AS (
    SELECT
        hw.driver_id,
        hw.year,
        hw.first_missed_round,
        hw.last_missed_round,
        hw.missed_races_count,
        hw.round_before_hiatus,
        hw.round_after_hiatus,
        (
            SELECT drs.constructor_id
            FROM driver_race_status AS drs
            WHERE drs.driver_id = hw.driver_id
              AND drs.year = hw.year
              AND drs.round = hw.round_before_hiatus
              AND drs.participated = 1
        ) AS constructor_before_hiatus,
        (
            SELECT drs.constructor_id
            FROM driver_race_status AS drs
            WHERE drs.driver_id = hw.driver_id
              AND drs.year = hw.year
              AND drs.round = hw.round_after_hiatus
              AND drs.participated = 1
        ) AS constructor_after_hiatus
    FROM hiatus_with_surrounding_races AS hw
    WHERE hw.round_before_hiatus IS NOT NULL
      AND hw.round_after_hiatus IS NOT NULL
),
final_hiatuses AS (
    SELECT
        driver_id,
        year,
        first_missed_round,
        last_missed_round
    FROM hiatus_with_constructors
    WHERE constructor_before_hiatus <> constructor_after_hiatus
)
SELECT
    AVG(first_missed_round),
    AVG(last_missed_round)
FROM final_hiatuses