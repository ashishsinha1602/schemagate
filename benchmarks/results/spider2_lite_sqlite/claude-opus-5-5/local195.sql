WITH actor_rentals AS (
  SELECT fa.actor_id, COUNT(*) AS rental_count
  FROM film_actor fa
  JOIN inventory i ON i.film_id = fa.film_id
  JOIN rental r ON r.inventory_id = i.inventory_id
  GROUP BY fa.actor_id
  ORDER BY rental_count DESC, fa.actor_id
  LIMIT 5
),
top_customers AS (
  SELECT DISTINCT r.customer_id
  FROM rental r
  JOIN inventory i ON i.inventory_id = r.inventory_id
  JOIN film_actor fa ON fa.film_id = i.film_id
  WHERE fa.actor_id IN (SELECT actor_id FROM actor_rentals)
)
SELECT ROUND(100.0 * (SELECT COUNT(*) FROM top_customers) / (SELECT COUNT(*) FROM customer), 2) AS pct_customers