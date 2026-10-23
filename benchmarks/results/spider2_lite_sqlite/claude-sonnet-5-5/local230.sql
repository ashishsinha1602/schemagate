WITH top_genres AS (
  SELECT g.genre
  FROM genre g
  JOIN ratings r ON r.movie_id = g.movie_id
  WHERE r.avg_rating > 8
  GROUP BY g.genre
  ORDER BY COUNT(DISTINCT g.movie_id) DESC
  LIMIT 3
)
SELECT n.name AS director_name, COUNT(DISTINCT dm.movie_id) AS movie_count
FROM director_mapping dm
JOIN names n ON n.id = dm.name_id
JOIN ratings r ON r.movie_id = dm.movie_id
JOIN genre g ON g.movie_id = dm.movie_id
WHERE r.avg_rating > 8
  AND g.genre IN (SELECT genre FROM top_genres)
GROUP BY dm.name_id, n.name
ORDER BY movie_count DESC, n.name
LIMIT 4