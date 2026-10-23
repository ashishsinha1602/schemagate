WITH DirectorMovieData AS (
  SELECT
    n.id AS director_id,
    n.name AS director_name,
    m.id AS movie_id,
    m.duration,
    m.date_published,
    r.avg_rating,
    r.total_votes
  FROM main.names AS n
  JOIN main.director_mapping AS dm ON n.id = dm.name_id
  JOIN main.movies AS m ON dm.movie_id = m.id
  JOIN main.ratings AS r ON m.id = r.movie_id
),
InterMovieDurations AS (
  SELECT
    director_id,
    director_name,
    date_published,
    LAG(date_published, 1, date_published) OVER (PARTITION BY director_id ORDER BY date_published) AS prev_date_published
  FROM DirectorMovieData
),
AvgInterMovieDuration AS (
  SELECT
    director_id,
    ROUND(AVG(JULIANDAY(date_published) - JULIANDAY(prev_date_published))) AS avg_inter_movie_duration_days
  FROM InterMovieDurations
  WHERE date_published != prev_date_published
  GROUP BY director_id
)
SELECT
  dmd.director_id,
  dmd.director_name,
  COUNT(DISTINCT dmd.movie_id) AS number_of_movies,
  COALESCE(aimd.avg_inter_movie_duration_days, 0) AS avg_inter_movie_duration,
  ROUND(AVG(dmd.avg_rating), 2) AS avg_rating,
  SUM(dmd.total_votes) AS total_votes,
  MIN(dmd.avg_rating) AS min_rating,
  MAX(dmd.avg_rating) AS max_rating,
  SUM(dmd.duration) AS total_movie_duration
FROM DirectorMovieData AS dmd
LEFT JOIN AvgInterMovieDuration AS aimd ON dmd.director_id = aimd.director_id
GROUP BY
  dmd.director_id,
  dmd.director_name
ORDER BY
  number_of_movies DESC,
  total_movie_duration DESC
LIMIT 9