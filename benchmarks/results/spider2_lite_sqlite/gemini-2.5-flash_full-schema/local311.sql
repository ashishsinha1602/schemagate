WITH DriverPointsPerConstructorPerYear AS (
    SELECT
        r.year,
        res.constructor_id,
        res.driver_id,
        SUM(res.points) AS driver_points_for_constructor
    FROM main.results AS res
    JOIN main.races AS r
        ON res.race_id = r.race_id
    GROUP BY
        r.year,
        res.constructor_id,
        res.driver_id
),
BestDriverPointsPerConstructorPerYear AS (
    SELECT
        year,
        constructor_id,
        MAX(driver_points_for_constructor) AS best_driver_points
    FROM DriverPointsPerConstructorPerYear
    GROUP BY
        year,
        constructor_id
),
ConstructorTotalPointsPerYear AS (
    SELECT
        r.year,
        cs.constructor_id,
        MAX(cs.points) AS constructor_total_points
    FROM main.constructor_standings AS cs
    JOIN main.races AS r
        ON cs.race_id = r.race_id
    GROUP BY
        r.year,
        cs.constructor_id
),
CombinedScores AS (
    SELECT
        bd.year,
        bd.constructor_id,
        bd.best_driver_points + ct.constructor_total_points AS combined_points
    FROM BestDriverPointsPerConstructorPerYear AS bd
    JOIN ConstructorTotalPointsPerYear AS ct
        ON bd.year = ct.year AND bd.constructor_id = ct.constructor_id
),
RankedCombinedScores AS (
    SELECT
        c.name AS constructor_name,
        cs.year,
        cs.combined_points,
        RANK() OVER (ORDER BY cs.combined_points DESC) AS rank_num
    FROM CombinedScores AS cs
    JOIN main.constructors AS c
        ON cs.constructor_id = c.constructor_id
)
SELECT
    constructor_name,
    year
FROM RankedCombinedScores
WHERE rank_num <= 3
ORDER BY
    rank_num,
    year,
    constructor_name