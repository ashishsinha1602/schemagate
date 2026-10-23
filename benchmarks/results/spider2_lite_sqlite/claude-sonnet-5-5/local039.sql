SELECT c.name AS category, SUM((julianday(r.return_date) - julianday(r.rental_date)) * 24) AS total_rental_hours
FROM rental r
JOIN customer_list cl ON cl.ID = r.customer_id
JOIN inventory i ON i.inventory_id = r.inventory_id
JOIN film_category fc ON fc.film_id = i.film_id
JOIN category c ON c.category_id = fc.category_id
WHERE r.return_date IS NOT NULL
  AND (cl.city LIKE 'A%' OR cl.city LIKE '%-%')
GROUP BY c.category_id, c.name
ORDER BY total_rental_hours DESC
LIMIT 1