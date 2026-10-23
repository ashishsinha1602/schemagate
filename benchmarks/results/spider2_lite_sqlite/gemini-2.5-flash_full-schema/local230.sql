WITH
  MoviesRatedAbove8 AS (
    SELECT
      m.id AS movie_id,
      g.genre
    FROM main.movies AS m
    JOIN main.ratings AS r
      ON m.id = r.movie_id
    JOIN main.genre AS g
      ON m.id = g.movie_id
    WHERE
      r.avg_rating > 8
  ),
  Top3Genres AS (
    SELECT
      genre
    FROM MoviesRatedAbove8
    GROUP BY
      genre
    ORDER BY
      COUNT(movie_id) DESC
    LIMIT 3
  ),
  DirectorMovieCounts AS (
    SELECT
      t3g.genre,
      n.name AS director_name,
      COUNT(mra8.movie_id) AS movie_count
    FROM MoviesRatedAbove8 AS mra8
    JOIN Top3Genres AS t3g
      ON mra8.genre = t3g.genre
    JOIN main.director_mapping AS dm
      ON mra8.movie_id = dm.movie_id
    JOIN main.names AS n
      ON dm.name_id = n.id
    GROUP BY
      t3g.genre,
      n.name
  ),
  RankedDirectors AS (
    SELECT
      genre,
      director_name,
      movie_count,
      ROW_NUMBER() OVER (PARTITION BY genre ORDER BY movie_count DESC) AS rn
    FROM DirectorMovieCounts
  )
SELECT
  genre,
  director_name,
  movie_count
FROM RankedDirectors
WHERE
  rn <= 4
ORDER BY
  genre,
  movie_count DESC