WITH top_actors AS (
  SELECT actor_id
  FROM film_actor
  GROUP BY actor_id
  ORDER BY COUNT(*) DESC, actor_id
  LIMIT 5
),
reached AS (
  SELECT DISTINCT r.customer_id
  FROM rental r
  JOIN inventory i ON i.inventory_id = r.inventory_id
  JOIN film_actor fa ON fa.film_id = i.film_id
  WHERE fa.actor_id IN (SELECT actor_id FROM top_actors)
)
SELECT 100.0 * (SELECT COUNT(*) FROM reached) / (SELECT COUNT(*) FROM customer) AS pct_customers