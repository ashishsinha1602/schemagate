WITH grid_positions AS (
    SELECT
        race_id,
        driver_id,
        grid
    FROM main.results
),
lap_positions_with_grid AS (
    SELECT
        lp.race_id,
        lp.driver_id,
        lp.lap,
        lp.position
    FROM main.lap_positions lp
    WHERE lp.lap BETWEEN 1 AND 5
    UNION ALL
    SELECT
        gp.race_id,
        gp.driver_id,
        0 AS lap, -- Represent grid as lap 0
        gp.grid AS position
    FROM grid_positions gp
),
all_overtakes AS (
    SELECT
        lp_curr_overtaking.race_id,
        lp_curr_overtaking.lap,
        lp_curr_overtaking.driver_id AS overtaking_driver_id,
        lp_curr.driver_id AS overtaken_driver_id,
        lp_prev_overtaking.position AS overtaking_driver_pos_prev_lap,
        lp_curr_overtaking.position AS overtaking_driver_pos_curr_lap,
        lp_prev.position AS overtaken_driver_pos_prev_lap,
        lp_curr.position AS overtaken_driver_pos_curr_lap
    FROM lap_positions_with_grid lp_curr_overtaking
    JOIN lap_positions_with_grid lp_prev_overtaking
        ON lp_curr_overtaking.race_id = lp_prev_overtaking.race_id
        AND lp_curr_overtaking.driver_id = lp_prev_overtaking.driver_id
        AND lp_curr_overtaking.lap = lp_prev_overtaking.lap + 1
    JOIN lap_positions_with_grid lp_curr
        ON lp_curr_overtaking.race_id = lp_curr.race_id
        AND lp_curr_overtaking.lap = lp_curr.lap
        AND lp_curr_overtaking.driver_id <> lp_curr.driver_id
    JOIN lap_positions_with_grid lp_prev
        ON lp_curr.race_id = lp_prev.race_id
        AND lp_curr.driver_id = lp_prev.driver_id
        AND lp_curr.lap = lp_prev.lap + 1
    WHERE
        lp_curr_overtaking.position < lp_curr.position -- Overtaking driver is ahead of overtaken driver on current lap
        AND lp_prev_overtaking.position > lp_prev.position -- Overtaking driver was behind overtaken driver on previous lap
)
SELECT
    SUM(CASE WHEN overtake_category = 'R' THEN 1 ELSE 0 END) AS Retirement_Overtakes,
    SUM(CASE WHEN overtake_category = 'P' THEN 1 ELSE 0 END) AS Pit_Overtakes,
    SUM(CASE WHEN overtake_category = 'S' THEN 1 ELSE 0 END) AS Start_Overtakes,
    SUM(CASE WHEN overtake_category = 'T' THEN 1 ELSE 0 END) AS Track_Overtakes
FROM (
    SELECT
        o.race_id,
        o.lap,
        o.overtaking_driver_id,
        o.overtaken_driver_id,
        CASE
            WHEN EXISTS (SELECT 1 FROM main.retirements r WHERE r.race_id = o.race_id AND r.driver_id = o.overtaken_driver_id AND r.lap = o.lap) THEN 'R'
            WHEN EXISTS (SELECT 1 FROM main.pit_stops ps WHERE ps.race_id = o.race_id AND ps.driver_id = o.overtaken_driver_id AND (ps.lap = o.lap OR ps.lap = o.lap - 1)) THEN 'P'
            WHEN o.lap = 1 AND ABS(gp_overtaking.grid - gp_overtaken.grid) <= 2 THEN 'S'
            ELSE 'T'
        END AS overtake_category
    FROM all_overtakes o
    LEFT JOIN grid_positions gp_overtaking
        ON o.race_id = gp_overtaking.race_id
        AND o.overtaking_driver_id = gp_overtaking.driver_id
    LEFT JOIN grid_positions gp_overtaken
        ON o.race_id = gp_overtaken.race_id
        AND o.overtaken_driver_id = gp_overtaken.driver_id
) AS classified_overtakes