WITH DriverSeasonPoints AS (
    SELECT
        r.year,
        ds.driver_id,
        SUM(ds.points) AS total_season_points
    FROM
        main.driver_standings ds
    JOIN
        main.races r ON ds.race_id = r.race_id
    WHERE
        r.year >= 2001
    GROUP BY
        r.year,
        ds.driver_id
    HAVING
        SUM(ds.points) > 0
),
MinPointsPerSeason AS (
    SELECT
        year,
        MIN(total_season_points) AS min_points
    FROM
        DriverSeasonPoints
    GROUP BY
        year
),
DriversWithMinPoints AS (
    SELECT
        dsp.year,
        dsp.driver_id
    FROM
        DriverSeasonPoints dsp
    JOIN
        MinPointsPerSeason mps ON dsp.year = mps.year AND dsp.total_season_points = mps.min_points
),
ConstructorsForMinPointDrivers AS (
    SELECT DISTINCT
        dwmp.year,
        res.constructor_id
    FROM
        DriversWithMinPoints dwmp
    JOIN
        main.results res ON dwmp.driver_id = res.driver_id
    JOIN
        main.races r ON res.race_id = r.race_id AND dwmp.year = r.year
)
SELECT
    c.name
FROM
    ConstructorsForMinPointDrivers cfd
JOIN
    main.constructors c ON cfd.constructor_id = c.constructor_id
GROUP BY
    c.name
ORDER BY
    COUNT(DISTINCT cfd.year) DESC
LIMIT 5