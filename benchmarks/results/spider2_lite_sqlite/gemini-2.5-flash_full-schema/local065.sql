SELECT
  SUM(
    CASE
      WHEN pn.pizza_name = 'Meatlovers' THEN 12
      WHEN pn.pizza_name = 'Vegetarian' THEN 10
      ELSE 0
    END + (
      CASE
        WHEN cco.extras IS NULL OR cco.extras = '' OR cco.extras = 'null' THEN 0
        ELSE LENGTH(cco.extras) - LENGTH(REPLACE(cco.extras, ',', '')) + 1
      END
    ) * 1
  )
FROM main.pizza_clean_customer_orders AS cco
JOIN main.pizza_names AS pn
  ON cco.pizza_id = pn.pizza_id
JOIN main.pizza_clean_runner_orders AS cro
  ON cco.order_id = cro.order_id
WHERE
  cro.cancellation IS NULL OR cro.cancellation = 'null'