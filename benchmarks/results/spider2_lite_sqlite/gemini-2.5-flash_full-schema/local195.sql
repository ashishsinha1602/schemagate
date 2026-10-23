WITH ActorRentalCounts AS (
    SELECT
        a.actor_id,
        COUNT(DISTINCT r.customer_id) AS distinct_customer_rentals
    FROM
        main.actor AS a
    JOIN
        main.film_actor AS fa ON a.actor_id = fa.actor_id
    JOIN
        main.inventory AS i ON fa.film_id = i.film_id
    JOIN
        main.rental AS r ON i.inventory_id = r.inventory_id
    GROUP BY
        a.actor_id
),
Top5Actors AS (
    SELECT
        actor_id
    FROM
        ActorRentalCounts
    ORDER BY
        distinct_customer_rentals DESC
    LIMIT 5
),
CustomersWhoRentedTop5ActorFilms AS (
    SELECT DISTINCT
        r.customer_id
    FROM
        main.rental AS r
    JOIN
        main.inventory AS i ON r.inventory_id = i.inventory_id
    JOIN
        main.film_actor AS fa ON i.film_id = fa.film_id
    JOIN
        Top5Actors AS t5a ON fa.actor_id = t5a.actor_id
)
SELECT
    CAST(COUNT(DISTINCT cwr.customer_id) AS REAL) * 100.0 / (SELECT COUNT(DISTINCT customer_id) FROM main.customer)
FROM
    CustomersWhoRentedTop5ActorFilms AS cwr