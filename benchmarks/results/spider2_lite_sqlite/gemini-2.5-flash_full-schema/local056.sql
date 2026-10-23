WITH monthly_payments AS (
  SELECT
    customer_id,
    STRFTIME('%Y-%m', payment_date) AS payment_month,
    SUM(amount) AS total_monthly_amount
  FROM main.payment
  GROUP BY
    customer_id,
    payment_month
), monthly_changes AS (
  SELECT
    customer_id,
    payment_month,
    total_monthly_amount,
    LAG(total_monthly_amount, 1, 0) OVER (PARTITION BY customer_id ORDER BY payment_month) AS previous_month_amount,
    total_monthly_amount - LAG(total_monthly_amount, 1, total_monthly_amount) OVER (PARTITION BY customer_id ORDER BY payment_month) AS monthly_change
  FROM monthly_payments
), average_monthly_change AS (
  SELECT
    customer_id,
    AVG(monthly_change) AS avg_change
  FROM monthly_changes
  WHERE
    previous_month_amount != total_monthly_amount -- Exclude the first month's "change" if it was 0, or if there was only one month
  GROUP BY
    customer_id
)
SELECT
  c.first_name || ' ' || c.last_name
FROM main.customer AS c
JOIN average_monthly_change AS amc
  ON c.customer_id = amc.customer_id
ORDER BY
  amc.avg_change DESC
LIMIT 1