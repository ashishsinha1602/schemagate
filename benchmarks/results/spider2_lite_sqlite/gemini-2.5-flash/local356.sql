WITH DriverLapPositions AS (
    SELECT
        lp.race_id,
        lp.driver_id,
        lp.lap,
        lp.position,
        LAG(lp.position, 1, lp.position) OVER (PARTITION BY lp.race_id, lp.driver_id ORDER BY lp.lap) AS previous_position
    FROM
        main.lap_positions AS lp
),
PitStopLaps AS (
    SELECT DISTINCT race_id, driver_id, lap
    FROM main.pit_stops
),
RetirementLaps AS (
    SELECT DISTINCT race_id, driver_id, lap
    FROM main.retirements
    WHERE lap IS NOT NULL -- Only consider retirements where the specific lap is known
),
ValidPositionChanges AS (
    SELECT
        dlp.driver_id,
        CASE
            WHEN dlp.position > dlp.previous_position THEN 1
            ELSE 0
        END AS overtaken_count,
        CASE
            WHEN dlp.position < dlp.previous_position THEN 1
            ELSE 0
        END AS overtakes_count
    FROM
        DriverLapPositions AS dlp
    LEFT JOIN
        PitStopLaps AS psl ON dlp.race_id = psl.race_id AND dlp.driver_id = psl.driver_id AND dlp.lap = psl.lap
    LEFT JOIN
        RetirementLaps AS rl ON dlp.race_id = rl.race_id AND dlp.driver_id = rl.driver_id AND dlp.lap = rl.lap
    WHERE
        dlp.lap > 1 -- Exclude position changes on the first lap
        AND psl.race_id IS NULL -- Exclude laps where a pit stop occurred
        AND rl.race_id IS NULL -- Exclude laps where a retirement occurred
        AND dlp.position != dlp.previous_position -- Only consider actual position changes
)
SELECT
    d.full_name
FROM
    ValidPositionChanges AS vpc
JOIN
    main.drivers AS d ON vpc.driver_id = d.driver_id
GROUP BY
    d.driver_id, d.full_name
HAVING
    SUM(vpc.overtaken_count) > SUM(vpc.overtakes_count)