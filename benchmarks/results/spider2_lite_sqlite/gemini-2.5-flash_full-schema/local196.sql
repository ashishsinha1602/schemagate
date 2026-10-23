WITH CustomerFirstRentalPayment AS (
    -- Find the earliest payment date for a rental for each customer
    -- and identify the corresponding rental_id.
    -- ROW_NUMBER handles ties in payment_date by payment_id.
    SELECT
        p.customer_id,
        p.rental_id,
        p.payment_date,
        ROW_NUMBER() OVER (PARTITION BY p.customer_id ORDER BY p.payment_date, p.payment_id) AS rn
    FROM
        main.payment AS p
    WHERE
        p.rental_id IS NOT NULL -- Only consider payments that are linked to a rental
),
FirstMovieRating AS (
    -- Determine the rating of the first movie rented by each customer.
    SELECT
        cfrp.customer_id,
        f.rating AS first_movie_rating
    FROM
        CustomerFirstRentalPayment AS cfrp
    JOIN
        main.rental AS r ON cfrp.rental_id = r.rental_id
    JOIN
        main.inventory AS i ON r.inventory_id = i.inventory_id
    JOIN
        main.film AS f ON i.film_id = f.film_id
    WHERE
        cfrp.rn = 1 -- Select only the first rental payment for each customer
),
CustomerAggregates AS (
    -- Calculate total amount spent and total number of rentals for each customer.
    SELECT
        c.customer_id,
        SUM(p.amount) AS total_spent,
        COUNT(r.rental_id) AS total_rentals,
        (COUNT(r.rental_id) - 1) AS subsequent_rentals -- Subsequent rentals = total rentals - 1
    FROM
        main.customer AS c
    JOIN
        main.payment AS p ON c.customer_id = p.customer_id
    JOIN
        main.rental AS r ON c.customer_id = r.customer_id
    GROUP BY
        c.customer_id
)
-- Final aggregation: group by the rating of the first movie and calculate averages.
SELECT
    fmr.first_movie_rating,
    AVG(ca.total_spent) AS average_total_amount_spent_per_customer,
    AVG(ca.subsequent_rentals) AS average_subsequent_rentals
FROM
    FirstMovieRating AS fmr
JOIN
    CustomerAggregates AS ca ON fmr.customer_id = ca.customer_id
GROUP BY
    fmr.first_movie_rating