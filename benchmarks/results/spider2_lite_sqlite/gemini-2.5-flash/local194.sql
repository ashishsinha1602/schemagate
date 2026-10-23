WITH FilmActorCounts AS (
    SELECT
        film_id,
        COUNT(actor_id) AS num_actors
    FROM main.film_actor
    GROUP BY film_id
),
FilmActorRevenueShare AS (
    SELECT
        fa.actor_id,
        f.film_id,
        f.title,
        CAST(f.rental_rate AS REAL) / fac.num_actors AS actor_share_revenue
    FROM main.film_actor AS fa
    JOIN main.film AS f
        ON fa.film_id = f.film_id
    JOIN FilmActorCounts AS fac
        ON f.film_id = fac.film_id
),
RankedActorFilms AS (
    SELECT
        far.actor_id,
        a.first_name,
        a.last_name,
        far.film_id,
        far.title,
        far.actor_share_revenue,
        ROW_NUMBER() OVER (PARTITION BY far.actor_id ORDER BY far.actor_share_revenue DESC, far.film_id) AS rn
    FROM FilmActorRevenueShare AS far
    JOIN main.actor AS a
        ON far.actor_id = a.actor_id
)
SELECT
    raf.first_name,
    raf.last_name,
    raf.title,
    raf.actor_share_revenue,
    AVG(raf.actor_share_revenue) OVER (PARTITION BY raf.actor_id) AS avg_actor_revenue_top3_films
FROM RankedActorFilms AS raf
WHERE raf.rn <= 3
ORDER BY
    raf.first_name,
    raf.last_name,
    raf.rn