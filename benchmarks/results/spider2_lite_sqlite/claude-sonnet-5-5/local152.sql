WITH dm AS (
  SELECT d.name_id, m.id AS movie_id, m.date_published, m.duration, r.avg_rating, r.total_votes,
         LAG(m.date_published) OVER (PARTITION BY d.name_id ORDER BY m.date_published) AS prev_date
  FROM director_mapping d
  JOIN movies m ON m.id = d.movie_id
  JOIN ratings r ON r.movie_id = m.id
)
SELECT dm.name_id AS director_id,
       n.name AS director_name,
       COUNT(*) AS number_of_movies,
       CAST(ROUND(AVG(julianday(dm.date_published) - julianday(dm.prev_date))) AS INTEGER) AS avg_inter_movie_duration,
       ROUND(AVG(dm.avg_rating), 2) AS avg_rating,
       SUM(dm.total_votes) AS total_votes,
       MIN(dm.avg_rating) AS min_rating,
       MAX(dm.avg_rating) AS max_rating,
       SUM(dm.duration) AS total_duration
FROM dm
JOIN names n ON n.id = dm.name_id
GROUP BY dm.name_id, n.name
ORDER BY number_of_movies DESC, total_duration DESC
LIMIT 9