WITH d AS (
  SELECT
    dm.name_id,
    n.name,
    m.id AS movie_id,
    m.date_published,
    m.duration,
    r.avg_rating,
    r.total_votes,
    LEAD(m.date_published) OVER (
      PARTITION BY dm.name_id
      ORDER BY m.date_published
    ) AS next_date
  FROM director_mapping dm
  JOIN names n ON n.id = dm.name_id
  JOIN movies m ON m.id = dm.movie_id
  LEFT JOIN ratings r ON r.movie_id = m.id
)
SELECT
  name_id AS director_id,
  name AS director_name,
  COUNT(movie_id) AS number_of_movies,
  CAST(ROUND(AVG(julianday(next_date) - julianday(date_published))) AS INTEGER) AS avg_inter_movie_duration,
  ROUND(AVG(avg_rating), 2) AS avg_rating,
  SUM(total_votes) AS total_votes,
  MIN(avg_rating) AS min_rating,
  MAX(avg_rating) AS max_rating,
  SUM(duration) AS total_duration
FROM d
GROUP BY name_id, name
ORDER BY number_of_movies DESC, total_duration DESC
LIMIT 9