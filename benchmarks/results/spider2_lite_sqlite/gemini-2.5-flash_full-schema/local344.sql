WITH RaceLapPositions AS (
    SELECT
        lp.race_id,
        lp.driver_id,
        lp.lap,
        lp.position
    FROM main.lap_positions AS lp
),
DriverGrids AS (
    SELECT
        r.race_id,
        r.driver_id,
        r.grid
    FROM main.results AS r
),
-- Identify overtakes that occur from lap 2 onwards
ActualOvertakes AS (
    SELECT
        curr.race_id,
        curr.lap,
        curr_b.driver_id AS overtaking_driver_id,
        curr.driver_id AS overtaken_driver_id,
        curr_b.position AS overtaking_driver_curr_pos,
        curr.position AS overtaken_driver_curr_pos,
        prev_b.position AS overtaking_driver_prev_pos,
        prev.position AS overtaken_driver_prev_pos,
        NULL AS overtaking_driver_grid, -- Grid positions are not relevant for non-lap 1 overtakes
        NULL AS overtaken_driver_grid
    FROM RaceLapPositions AS curr -- The driver who was overtaken
    JOIN RaceLapPositions AS prev -- Their position on the previous lap
        ON curr.race_id = prev.race_id
        AND curr.driver_id = prev.driver_id
        AND curr.lap = prev.lap + 1
    JOIN RaceLapPositions AS curr_b -- The driver who did the overtaking
        ON curr.race_id = curr_b.race_id
        AND curr.lap = curr_b.lap
        AND curr.driver_id <> curr_b.driver_id
    JOIN RaceLapPositions AS prev_b -- Their position on the previous lap
        ON curr_b.race_id = prev_b.race_id
        AND curr_b.driver_id = prev_b.driver_id
        AND curr_b.lap = prev_b.lap + 1
    WHERE curr.lap > 1 -- Only consider laps after the first
      AND prev.position < prev_b.position -- Overtaken driver was ahead of overtaking driver on previous lap
      AND curr.position > curr_b.position   -- Overtaken driver is now behind overtaking driver on current lap
),
-- Identify overtakes that occur on lap 1 (compared to grid position)
Lap1Overtakes AS (
    SELECT
        lp_overtaken.race_id,
        1 AS lap,
        lp_overtaking.driver_id AS overtaking_driver_id,
        lp_overtaken.driver_id AS overtaken_driver_id,
        lp_overtaking.position AS overtaking_driver_curr_pos,
        lp_overtaken.position AS overtaken_driver_curr_pos,
        dg_overtaking.grid AS overtaking_driver_prev_pos, -- Grid position acts as 'previous lap' for lap 1
        dg_overtaken.grid AS overtaken_driver_prev_pos,
        dg_overtaking.grid AS overtaking_driver_grid,
        dg_overtaken.grid AS overtaken_driver_grid
    FROM RaceLapPositions AS lp_overtaken -- The driver who was overtaken
    JOIN RaceLapPositions AS lp_overtaking -- The driver who did the overtaking
        ON lp_overtaken.race_id = lp_overtaking.race_id
        AND lp_overtaken.lap = lp_overtaking.lap
        AND lp_overtaken.driver_id <> lp_overtaking.driver_id
    JOIN DriverGrids AS dg_overtaken
        ON lp_overtaken.race_id = dg_overtaken.race_id
        AND lp_overtaken.driver_id = dg_overtaken.driver_id
    JOIN DriverGrids AS dg_overtaking
        ON lp_overtaking.race_id = dg_overtaking.race_id
        AND lp_overtaking.driver_id = dg_overtaking.driver_id
    WHERE lp_overtaken.lap = 1
      AND dg_overtaken.grid < dg_overtaking.grid -- Overtaken driver started ahead of overtaking driver
      AND lp_overtaken.position > lp_overtaking.position -- Overtaken driver is now behind overtaking driver
),
-- Combine all identified overtake events
AllOvertakes AS (
    SELECT * FROM ActualOvertakes
    UNION ALL
    SELECT * FROM Lap1Overtakes
),
-- Filter for races where pit stop data is available
FilteredOvertakes AS (
    SELECT
        ao.race_id,
        ao.lap,
        ao.overtaking_driver_id,
        ao.overtaken_driver_id,
        ao.overtaking_driver_curr_pos,
        ao.overtaken_driver_curr_pos,
        ao.overtaking_driver_prev_pos,
        ao.overtaken_driver_prev_pos,
        ao.overtaking_driver_grid,
        ao.overtaken_driver_grid
    FROM AllOvertakes AS ao
    JOIN main.races_ext AS re ON ao.race_id = re.race_id
    WHERE re.is_pit_data_available = 1
),
-- Classify each overtake based on the defined rules
ClassifiedOvertakes AS (
    SELECT
        fo.race_id,
        fo.lap,
        fo.overtaking_driver_id,
        fo.overtaken_driver_id,
        CASE
            -- Rule 1: R (Retirement) - Overtaken driver retired on the same lap
            WHEN EXISTS (
                SELECT 1 FROM main.retirements AS r
                WHERE r.race_id = fo.race_id
                  AND r.driver_id = fo.overtaken_driver_id
                  AND r.lap = fo.lap
            ) THEN 'R'
            -- Rule 2: P (Pit) - Overtaken driver pitted on the same lap (entry) or previous lap (exit)
            WHEN EXISTS (
                SELECT 1 FROM main.pit_stops AS ps
                WHERE ps.race_id = fo.race_id
                  AND ps.driver_id = fo.overtaken_driver_id
                  AND (ps.lap = fo.lap OR ps.lap = fo.lap - 1)
            ) THEN 'P'
            -- Rule 3: S (Start) - Overtake on lap 1, and drivers were within two grid positions
            WHEN fo.lap = 1
                 AND ABS(fo.overtaking_driver_grid - fo.overtaken_driver_grid) <= 2
                 THEN 'S'
            -- Rule 4: T (Track) - Default if none of the above apply
            ELSE 'T'
        END AS overtake_type
    FROM FilteredOvertakes AS fo
)
-- Count the occurrences of each overtake type
SELECT
    overtake_type,
    COUNT(*) AS count
FROM ClassifiedOvertakes
GROUP BY overtake_type
ORDER BY overtake_type