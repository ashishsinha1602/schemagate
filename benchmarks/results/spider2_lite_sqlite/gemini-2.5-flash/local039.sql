SELECT
  T4.name
FROM main.rental AS T1
INNER JOIN main.customer_list AS T2
  ON T1.customer_id = T2.ID
INNER JOIN main.inventory AS T3
  ON T1.inventory_id = T3.inventory_id
INNER JOIN main.film_category AS T5
  ON T3.film_id = T5.film_id
INNER JOIN main.category AS T4
  ON T5.category_id = T4.category_id
WHERE
  T2.city LIKE 'A%' OR T2.city LIKE '%-%' AND T1.return_date IS NOT NULL
GROUP BY
  T4.name
ORDER BY
  SUM(JULIANDAY(T1.return_date) - JULIANDAY(T1.rental_date)) DESC
LIMIT 1