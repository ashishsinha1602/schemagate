SELECT SUM(
  CASE WHEN c.pizza_id = 1 THEN 12 ELSE 10 END
  + CASE
      WHEN c.extras IS NULL OR TRIM(c.extras) = '' OR LOWER(TRIM(c.extras)) = 'null' THEN 0
      ELSE LENGTH(c.extras) - LENGTH(REPLACE(c.extras, ',', '')) + 1
    END
) AS total_income
FROM pizza_clean_customer_orders c
JOIN pizza_clean_runner_orders r ON r.order_id = c.order_id
WHERE r.cancellation IS NULL
   OR TRIM(r.cancellation) = ''
   OR LOWER(TRIM(r.cancellation)) = 'null'