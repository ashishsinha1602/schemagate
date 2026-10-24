WITH first_pay AS (
  SELECT p.customer_id, p.rental_id,
         ROW_NUMBER() OVER (PARTITION BY p.customer_id ORDER BY p.payment_date, p.payment_id) AS rn
  FROM payment p
),
first_rating AS (
  SELECT fp.customer_id, f.rating
  FROM first_pay fp
  JOIN rental r ON r.rental_id = fp.rental_id
  JOIN inventory i ON i.inventory_id = r.inventory_id
  JOIN film f ON f.film_id = i.film_id
  WHERE fp.rn = 1
),
cust_totals AS (
  SELECT customer_id, SUM(amount) AS total_amount
  FROM payment
  GROUP BY customer_id
),
cust_rentals AS (
  SELECT customer_id, COUNT(*) AS rental_count
  FROM rental
  GROUP BY customer_id
)
SELECT fr.rating,
       AVG(ct.total_amount) AS avg_total_amount,
       AVG(COALESCE(cr.rental_count, 0) - 1) AS avg_subsequent_rentals
FROM first_rating fr
JOIN cust_totals ct ON ct.customer_id = fr.customer_id
LEFT JOIN cust_rentals cr ON cr.customer_id = fr.customer_id
GROUP BY fr.rating