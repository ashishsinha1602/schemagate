SELECT
  T1.first_name || ' ' || T1.last_name
FROM main.actor AS T1
INNER JOIN main.film_actor AS T2
  ON T1.actor_id = T2.actor_id
INNER JOIN main.film AS T3
  ON T2.film_id = T3.film_id
INNER JOIN main.language AS T4
  ON T3.language_id = T4.language_id
INNER JOIN main.film_category AS T5
  ON T3.film_id = T5.film_id
INNER JOIN main.category AS T6
  ON T5.category_id = T6.category_id
WHERE
  T4.name = 'English' AND T6.name = 'Children' AND T3.rating IN ('G', 'PG') AND T3.length <= 120 AND T3.release_year BETWEEN '2000' AND '2010'
GROUP BY
  T1.actor_id,
  T1.first_name,
  T1.last_name
ORDER BY
  COUNT(DISTINCT T3.film_id) DESC
LIMIT 1