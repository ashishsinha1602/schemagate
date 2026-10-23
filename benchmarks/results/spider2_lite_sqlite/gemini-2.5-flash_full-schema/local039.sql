SELECT
  T5.name
FROM main.rental AS T1
INNER JOIN main.customer AS T2
  ON T1.customer_id = T2.customer_id
INNER JOIN main.address AS T3
  ON T2.address_id = T3.address_id
INNER JOIN main.city AS T4
  ON T3.city_id = T4.city_id
INNER JOIN main.inventory AS T6
  ON T1.inventory_id = T6.inventory_id
INNER JOIN main.film AS T7
  ON T6.film_id = T7.film_id
INNER JOIN main.film_category AS T8
  ON T7.film_id = T8.film_id
INNER JOIN main.category AS T5
  ON T8.category_id = T5.category_id
WHERE
  T4.city LIKE 'A%' OR T4.city LIKE '%-%'
GROUP BY
  T5.name
ORDER BY
  SUM(T7.length) DESC
LIMIT 1