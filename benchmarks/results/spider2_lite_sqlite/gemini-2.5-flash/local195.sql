WITH ActorRentalCounts AS (
    SELECT
        fa.actor_id,
        COUNT(r.rental_id) AS total_rentals
    FROM
        main.film_actor AS fa
    JOIN
        main.inventory AS i ON fa.film_id = i.film_id
    JOIN
        main.rental AS r ON i.inventory_id = r.inventory_id
    GROUP BY
        fa.actor_id
),
Top5Actors AS (
    SELECT
        actor_id
    FROM
        ActorRentalCounts
    ORDER BY
        total_rentals DESC
    LIMIT 5
),
CustomersWhoRentedTopActorFilms AS (
    SELECT DISTINCT
        r.customer_id
    FROM
        main.rental AS r
    JOIN
        main.inventory AS i ON r.inventory_id = i.inventory_id
    JOIN
        main.film_actor AS fa ON i.film_id = fa.film_id
    WHERE
        fa.actor_id IN (SELECT actor_id FROM Top5Actors)
)
SELECT
    CAST(COUNT(DISTINCT cwr.customer_id) AS REAL) * 100.0 / (SELECT COUNT(DISTINCT customer_id) FROM main.customer)
FROM
    CustomersWhoRentedTopActorFilms AS cwr