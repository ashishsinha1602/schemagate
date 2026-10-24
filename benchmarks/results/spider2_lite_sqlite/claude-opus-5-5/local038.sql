SELECT a.first_name || ' ' || a.last_name AS full_name
FROM actor a
JOIN film_actor fa ON fa.actor_id = a.actor_id
JOIN film f ON f.film_id = fa.film_id
JOIN language l ON l.language_id = f.language_id
JOIN film_category fc ON fc.film_id = f.film_id
JOIN category c ON c.category_id = fc.category_id
WHERE l.name = 'English'
  AND c.name = 'Children'
  AND f.rating IN ('G', 'PG')
  AND f.length <= 120
  AND CAST(f.release_year AS INTEGER) BETWEEN 2000 AND 2010
GROUP BY a.actor_id, a.first_name, a.last_name
ORDER BY COUNT(*) DESC
LIMIT 1