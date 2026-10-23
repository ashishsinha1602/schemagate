WITH driver_yearly_points AS (
    SELECT
        r.year,
        ds.driver_id,
        MAX(ds.points) AS driver_points
    FROM
        main.driver_standings AS ds
    JOIN
        main.races AS r
        ON ds.race_id = r.race_id
    GROUP BY
        r.year,
        ds.driver_id
),
best_driver_per_constructor_yearly AS (
    SELECT
        dy.year,
        tdr.constructor_id,
        MAX(dy.driver_points) AS best_driver_points
    FROM
        driver_yearly_points AS dy
    JOIN
        main.team_driver_ranks AS tdr
        ON dy.driver_id = tdr.driver_id AND dy.year = tdr.year
    GROUP BY
        dy.year,
        tdr.constructor_id
),
constructor_yearly_points AS (
    SELECT
        r.year,
        cs.constructor_id,
        MAX(cs.points) AS constructor_points
    FROM
        main.constructor_standings AS cs
    JOIN
        main.races AS r
        ON cs.race_id = r.race_id
    GROUP BY
        r.year,
        cs.constructor_id
)
SELECT
    c.name,
    bd.year,
    (bd.best_driver_points + cp.constructor_points) AS combined_points
FROM
    best_driver_per_constructor_yearly AS bd
JOIN
    constructor_yearly_points AS cp
    ON bd.year = cp.year AND bd.constructor_id = cp.constructor_id
JOIN
    main.constructors AS c
    ON bd.constructor_id = c.constructor_id
ORDER BY
    combined_points DESC
LIMIT 3