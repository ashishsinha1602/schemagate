WITH first_pay AS (
  SELECT customer_id, rental_id
  FROM (
    SELECT p.customer_id, p.rental_id,
           ROW_NUMBER() OVER (PARTITION BY p.customer_id ORDER BY p.payment_date, p.payment_id) AS rn
    FROM payment p
    WHERE p.rental_id IS NOT NULL
  )
  WHERE rn = 1
),
spent AS (
  SELECT customer_id, SUM(amount) AS total_spent
  FROM payment
  GROUP BY customer_id
),
rentals AS (
  SELECT customer_id, COUNT(*) AS rental_cnt
  FROM rental
  GROUP BY customer_id
)
SELECT f.rating,
       AVG(s.total_spent) AS avg_total_spent_per_customer,
       AVG(r.rental_cnt - 1) AS avg_subsequent_rentals
FROM first_pay fp
JOIN rental r0 ON r0.rental_id = fp.rental_id
JOIN inventory i ON i.inventory_id = r0.inventory_id
JOIN film f ON f.film_id = i.film_id
JOIN spent s ON s.customer_id = fp.customer_id
JOIN rentals r ON r.customer_id = fp.customer_id
GROUP BY f.rating