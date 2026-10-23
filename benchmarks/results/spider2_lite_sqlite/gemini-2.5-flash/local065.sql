WITH OrderDetails AS (
    SELECT
        pco.order_id,
        pco.pizza_id,
        pn.pizza_name,
        pco.extras,
        CASE
            WHEN pn.pizza_name = 'Meatlovers' THEN 12
            WHEN pn.pizza_name = 'Vegetarian' THEN 10
            ELSE 0
        END AS base_pizza_price,
        CASE
            WHEN pco.extras IS NULL OR pco.extras = '' OR pco.extras = 'null' THEN 0
            ELSE LENGTH(pco.extras) - LENGTH(REPLACE(pco.extras, ',', '')) + 1
        END AS num_extras
    FROM
        main.pizza_customer_orders AS pco
    JOIN
        main.pizza_names AS pn
        ON pco.pizza_id = pn.pizza_id
    JOIN
        main.pizza_clean_runner_orders AS pcro
        ON pco.order_id = pcro.order_id
    WHERE
        pcro.cancellation NOT IN ('Customer Cancelled', 'Runner Cancelled')
)
SELECT
    SUM(od.base_pizza_price + (od.num_extras * 1)) AS total_income
FROM
    OrderDetails AS od