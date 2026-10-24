WITH monthly AS (
  SELECT st.store_id,
         strftime('%Y', r.rental_date) AS year,
         strftime('%m', r.rental_date) AS month,
         COUNT(*) AS total_rentals
  FROM rental r
  JOIN staff st ON st.staff_id = r.staff_id
  GROUP BY st.store_id, year, month
),
ranked AS (
  SELECT *, RANK() OVER (PARTITION BY store_id ORDER BY total_rentals DESC) AS rnk
  FROM monthly
)
SELECT store_id, year, month, total_rentals
FROM ranked
WHERE rnk = 1
ORDER BY store_id