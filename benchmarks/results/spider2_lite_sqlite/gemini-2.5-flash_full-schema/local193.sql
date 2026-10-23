WITH first_rental_date AS (
  SELECT
    customer_id,
    MIN(rental_date) AS first_purchase_date
  FROM main.rental
  GROUP BY
    customer_id
), customer_ltv_details AS (
  SELECT
    p.customer_id,
    SUM(p.amount) AS total_ltv,
    SUM(CASE WHEN p.payment_date <= DATETIME(frd.first_purchase_date, '+7 days') THEN p.amount ELSE 0 END) AS sales_7_days,
    SUM(CASE WHEN p.payment_date <= DATETIME(frd.first_purchase_date, '+30 days') THEN p.amount ELSE 0 END) AS sales_30_days
  FROM main.payment AS p
  JOIN first_rental_date AS frd
    ON p.customer_id = frd.customer_id
  GROUP BY
    p.customer_id
)
SELECT
  AVG(t.sales_7_days * 100.0 / t.total_ltv) AS avg_percentage_7_days,
  AVG(t.sales_30_days * 100.0 / t.total_ltv) AS avg_percentage_30_days,
  AVG(t.total_ltv) AS avg_total_lifetime_sales
FROM customer_ltv_details AS t
WHERE
  t.total_ltv > 0