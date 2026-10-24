WITH top_genres AS (
  SELECT g.genre, COUNT(DISTINCT g.movie_id) AS movie_count
  FROM genre g
  JOIN ratings r ON r.movie_id = g.movie_id
  WHERE r.avg_rating > 8
  GROUP BY g.genre
  ORDER BY movie_count DESC
  LIMIT 3
)
SELECT n.name AS director_name, COUNT(DISTINCT d.movie_id) AS movie_count
FROM director_mapping d
JOIN ratings r ON r.movie_id = d.movie_id
JOIN genre g ON g.movie_id = d.movie_id
JOIN top_genres tg ON tg.genre = g.genre
JOIN names n ON n.id = d.name_id
WHERE r.avg_rating > 8
GROUP BY d.name_id, n.name
ORDER BY movie_count DESC
LIMIT 4