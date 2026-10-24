SELECT SUM(
         CASE WHEN pn.pizza_name LIKE 'Meat%' THEN 12 ELSE 10 END
         + CASE WHEN c.extras IS NULL OR TRIM(c.extras) IN ('', 'null') THEN 0
                ELSE LENGTH(c.extras) - LENGTH(REPLACE(c.extras, ',', '')) + 1 END
       ) AS total_income
FROM pizza_clean_customer_orders c
JOIN pizza_clean_runner_orders r ON r.order_id = c.order_id
JOIN pizza_names pn ON pn.pizza_id = c.pizza_id
WHERE r.cancellation IS NULL OR TRIM(r.cancellation) IN ('', 'null')