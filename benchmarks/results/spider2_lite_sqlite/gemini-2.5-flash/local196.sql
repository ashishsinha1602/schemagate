WITH CustomerFirstRental AS (
    SELECT
        p.customer_id,
        p.rental_id,
        p.payment_date,
        ROW_NUMBER() OVER (PARTITION BY p.customer_id ORDER BY p.payment_date ASC, p.payment_id ASC) as rn
    FROM
        main.payment AS p
    WHERE
        p.rental_id IS NOT NULL
),
FirstRentalFilmRating AS (
    SELECT
        cfr.customer_id,
        f.rating AS first_film_rating
    FROM
        CustomerFirstRental AS cfr
    JOIN
        main.rental AS r ON cfr.rental_id = r.rental_id
    JOIN
        main.inventory AS i ON r.inventory_id = i.inventory_id
    JOIN
        main.film AS f ON i.film_id = f.film_id
    WHERE
        cfr.rn = 1
),
CustomerTotalSpend AS (
    SELECT
        customer_id,
        SUM(amount) AS total_spent
    FROM
        main.payment
    GROUP BY
        customer_id
),
CustomerTotalRentals AS (
    SELECT
        customer_id,
        COUNT(rental_id) AS total_rentals
    FROM
        main.rental
    GROUP BY
        customer_id
)
SELECT
    frfr.first_film_rating AS rating_category,
    AVG(cts.total_spent) AS average_total_amount_spent_per_customer,
    AVG(CAST(ctr.total_rentals - 1 AS REAL)) AS average_subsequent_rentals
FROM
    FirstRentalFilmRating AS frfr
JOIN
    CustomerTotalSpend AS cts ON frfr.customer_id = cts.customer_id
JOIN
    CustomerTotalRentals AS ctr ON frfr.customer_id = ctr.customer_id
GROUP BY
    frfr.first_film_rating