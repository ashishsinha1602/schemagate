WITH DriverSeasonPoints AS (
    SELECT
        ds.driver_id,
        r.year,
        MAX(ds.points) AS total_driver_points
    FROM main.driver_standings AS ds
    JOIN main.races AS r
        ON ds.race_id = r.race_id
    WHERE r.year >= 2001
    GROUP BY
        ds.driver_id,
        r.year
    HAVING MAX(ds.points) > 0
),
ConstructorSeasonTotalDriverPoints AS (
    SELECT
        dsp.year,
        d.constructor_id,
        SUM(dsp.total_driver_points) AS constructor_total_driver_points
    FROM DriverSeasonPoints AS dsp
    JOIN main.drives AS d
        ON dsp.driver_id = d.driver_id AND dsp.year = d.year
    GROUP BY
        dsp.year,
        d.constructor_id
    HAVING SUM(dsp.total_driver_points) > 0
),
MinPointsPerSeason AS (
    SELECT
        year,
        MIN(constructor_total_driver_points) AS min_season_points
    FROM ConstructorSeasonTotalDriverPoints
    GROUP BY
        year
),
ConstructorsWithFewestPoints AS (
    SELECT
        cstdp.year,
        cstdp.constructor_id
    FROM ConstructorSeasonTotalDriverPoints AS cstdp
    JOIN MinPointsPerSeason AS mpps
        ON cstdp.year = mpps.year
        AND cstdp.constructor_total_driver_points = mpps.min_season_points
)
SELECT
    c.name
FROM ConstructorsWithFewestPoints AS cwfp
JOIN main.constructors AS c
    ON cwfp.constructor_id = c.constructor_id
GROUP BY
    c.name
ORDER BY
    COUNT(cwfp.year) DESC,
    c.name ASC
LIMIT 5