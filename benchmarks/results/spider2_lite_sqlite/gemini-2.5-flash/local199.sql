WITH MonthlyRentals AS (
  SELECT
    s.store_id,
    CAST(strftime('%Y', r.rental_date) AS INTEGER) AS rental_year,
    CAST(strftime('%m', r.rental_date) AS INTEGER) AS rental_month,
    COUNT(r.rental_id) AS total_rentals
  FROM main.rental AS r
  JOIN main.staff AS s
    ON r.staff_id = s.staff_id
  GROUP BY
    s.store_id,
    rental_year,
    rental_month
), RankedMonthlyRentals AS (
  SELECT
    store_id,
    rental_year,
    rental_month,
    total_rentals,
    RANK() OVER (PARTITION BY store_id ORDER BY total_rentals DESC) AS rn
  FROM MonthlyRentals
)
SELECT
  store_id,
  rental_year,
  rental_month,
  total_rentals
FROM RankedMonthlyRentals
WHERE
  rn = 1