WITH FilmTotalRevenue AS (
    SELECT
        f.film_id,
        SUM(p.amount) AS total_revenue
    FROM
        main.film AS f
    JOIN
        main.inventory AS i ON f.film_id = i.film_id
    JOIN
        main.rental AS r ON i.inventory_id = r.inventory_id
    JOIN
        main.payment AS p ON r.rental_id = p.rental_id
    GROUP BY
        f.film_id
), FilmActorCount AS (
    SELECT
        fa.film_id,
        COUNT(fa.actor_id) AS num_actors
    FROM
        main.film_actor AS fa
    GROUP BY
        fa.film_id
), FilmActorShareRevenue AS (
    SELECT
        ftr.film_id,
        CAST(ftr.total_revenue AS REAL) / fac.num_actors AS actor_share_revenue
    FROM
        FilmTotalRevenue AS ftr
    JOIN
        FilmActorCount AS fac ON ftr.film_id = fac.film_id
), ActorFilmRank AS (
    SELECT
        a.actor_id,
        a.first_name,
        a.last_name,
        f.film_id,
        f.title,
        fasr.actor_share_revenue,
        ROW_NUMBER() OVER (PARTITION BY a.actor_id ORDER BY fasr.actor_share_revenue DESC) AS rn
    FROM
        main.actor AS a
    JOIN
        main.film_actor AS fa ON a.actor_id = fa.actor_id
    JOIN
        main.film AS f ON fa.film_id = f.film_id
    JOIN
        FilmActorShareRevenue AS fasr ON f.film_id = fasr.film_id
)
SELECT
    afr.first_name,
    afr.last_name,
    afr.title AS film_title,
    afr.actor_share_revenue,
    AVG(afr.actor_share_revenue) OVER (PARTITION BY afr.actor_id) AS avg_revenue_top3_films
FROM
    ActorFilmRank AS afr
WHERE
    afr.rn <= 3
ORDER BY
    afr.first_name,
    afr.last_name,
    afr.rn