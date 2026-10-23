WITH driver_lap_positions AS (
    SELECT
        race_id,
        driver_id,
        lap,
        position,
        LAG(position, 1) OVER (PARTITION BY race_id, driver_id ORDER BY lap) AS prev_position
    FROM main.lap_positions
),
pit_stop_affected_laps AS (
    -- Identify laps where a pit stop occurred (entry) and the subsequent lap (exit effects)
    SELECT DISTINCT race_id, driver_id, lap FROM main.pit_stops
    UNION
    SELECT DISTINCT race_id, driver_id, lap + 1 AS lap FROM main.pit_stops
),
retirement_laps AS (
    -- Identify laps where a driver retired
    SELECT DISTINCT race_id, driver_id, lap
    FROM main.retirements
    WHERE lap IS NOT NULL
),
on_track_changes AS (
    SELECT
        dlp.driver_id,
        CASE
            WHEN dlp.position < dlp.prev_position THEN dlp.prev_position - dlp.position
            ELSE 0
        END AS overtakes_count,
        CASE
            WHEN dlp.position > dlp.prev_position THEN dlp.position - dlp.prev_position
            ELSE 0
        END AS overtaken_count
    FROM driver_lap_positions AS dlp
    WHERE
        dlp.lap > 1 -- Exclude first lap changes (considered as start movements)
        AND dlp.prev_position IS NOT NULL -- Ensure there was a previous position to compare
        AND NOT EXISTS (
            SELECT 1
            FROM pit_stop_affected_laps ps
            WHERE ps.race_id = dlp.race_id
              AND ps.driver_id = dlp.driver_id
              AND ps.lap = dlp.lap
        )
        AND NOT EXISTS (
            SELECT 1
            FROM retirement_laps r
            WHERE r.race_id = dlp.race_id
              AND r.driver_id = dlp.driver_id
              AND r.lap = dlp.lap
        )
)
SELECT
    d.full_name
FROM on_track_changes AS otc
JOIN main.drivers AS d
    ON otc.driver_id = d.driver_id
GROUP BY
    d.driver_id, d.full_name
HAVING
    SUM(otc.overtaken_count) < SUM(otc.overtaken_count)