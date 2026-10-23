WITH DirectorMovieInfo AS (
    SELECT
        dm.name_id,
        m.id AS movie_id,
        m.date_published,
        m.duration,
        r.avg_rating,
        r.total_votes
    FROM main.director_mapping AS dm
    JOIN main.movies AS m
        ON dm.movie_id = m.id
    JOIN main.ratings AS r
        ON dm.movie_id = r.movie_id
),
DirectorMovieDates AS (
    SELECT
        name_id,
        movie_id,
        date_published,
        LAG(date_published) OVER (PARTITION BY name_id ORDER BY date_published) AS prev_date_published
    FROM DirectorMovieInfo
),
InterMovieDurations AS (
    SELECT
        name_id,
        (julianday(date_published) - julianday(prev_date_published)) AS inter_duration_days
    FROM DirectorMovieDates
    WHERE prev_date_published IS NOT NULL
)
SELECT
    n.id AS director_id,
    n.name AS director_name,
    COUNT(DISTINCT dmi.movie_id) AS movie_count,
    ROUND(AVG(imd.inter_duration_days)) AS avg_inter_movie_duration,
    ROUND(AVG(dmi.avg_rating), 2) AS avg_rating,
    SUM(dmi.total_votes) AS total_votes,
    MIN(dmi.avg_rating) AS min_rating,
    MAX(dmi.avg_rating) AS max_rating,
    SUM(dmi.duration) AS total_movie_duration
FROM main.names AS n
JOIN DirectorMovieInfo AS dmi
    ON n.id = dmi.name_id
LEFT JOIN InterMovieDurations AS imd
    ON n.id = imd.name_id
GROUP BY
    n.id,
    n.name
ORDER BY
    movie_count DESC,
    total_movie_duration DESC
LIMIT 9