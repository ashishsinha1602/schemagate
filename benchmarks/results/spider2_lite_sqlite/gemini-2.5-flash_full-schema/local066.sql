WITH delivered_orders AS (
    SELECT
        pco.order_id,
        pco.pizza_id,
        pco.exclusions,
        pco.extras
    FROM main.pizza_customer_orders AS pco
    JOIN main.pizza_runner_orders AS pro
        ON pco.order_id = pro.order_id
    WHERE
        pro.cancellation IS NULL OR pro.cancellation = ''
),
split_recipes AS (
    WITH RECURSIVE sr_rec(pizza_id, topping_id_str, rest) AS (
        SELECT
            pr.pizza_id,
            CASE
                WHEN INSTR(pr.toppings, ',') > 0 THEN SUBSTR(pr.toppings, 1, INSTR(pr.toppings, ',') - 1)
                ELSE pr.toppings
            END,
            CASE
                WHEN INSTR(pr.toppings, ',') > 0 THEN SUBSTR(pr.toppings, INSTR(pr.toppings, ',') + 1)
                ELSE ''
            END
        FROM main.pizza_recipes AS pr
        UNION ALL
        SELECT
            s.pizza_id,
            CASE
                WHEN INSTR(s.rest, ',') > 0 THEN SUBSTR(s.rest, 1, INSTR(s.rest, ',') - 1)
                ELSE s.rest
            END,
            CASE
                WHEN INSTR(s.rest, ',') > 0 THEN SUBSTR(s.rest, INSTR(s.rest, ',') + 1)
                ELSE ''
            END
        FROM sr_rec AS s
        WHERE
            s.rest != ''
    )
    SELECT
        pizza_id,
        CAST(topping_id_str AS INTEGER) AS topping_id
    FROM sr_rec
    WHERE
        topping_id_str != ''
),
split_exclusions AS (
    WITH RECURSIVE se_rec(order_id, pizza_id, topping_id_str, rest) AS (
        SELECT
            do.order_id,
            do.pizza_id,
            CASE
                WHEN INSTR(do.exclusions, ',') > 0 THEN SUBSTR(do.exclusions, 1, INSTR(do.exclusions, ',') - 1)
                ELSE do.exclusions
            END,
            CASE
                WHEN INSTR(do.exclusions, ',') > 0 THEN SUBSTR(do.exclusions, INSTR(do.exclusions, ',') + 1)
                ELSE ''
            END
        FROM delivered_orders AS do
        WHERE
            do.exclusions IS NOT NULL AND do.exclusions != ''
        UNION ALL
        SELECT
            se.order_id,
            se.pizza_id,
            CASE
                WHEN INSTR(se.rest, ',') > 0 THEN SUBSTR(se.rest, 1, INSTR(se.rest, ',') - 1)
                ELSE se.rest
            END,
            CASE
                WHEN INSTR(se.rest, ',') > 0 THEN SUBSTR(se.rest, INSTR(se.rest, ',') + 1)
                ELSE ''
            END
        FROM se_rec AS se
        WHERE
            se.rest != ''
    )
    SELECT
        order_id,
        pizza_id,
        CAST(topping_id_str AS INTEGER) AS topping_id
    FROM se_rec
    WHERE
        topping_id_str != ''
),
split_extras AS (
    WITH RECURSIVE sx_rec(order_id, pizza_id, topping_id_str, rest) AS (
        SELECT
            do.order_id,
            do.pizza_id,
            CASE
                WHEN INSTR(do.extras, ',') > 0 THEN SUBSTR(do.extras, 1, INSTR(do.extras, ',') - 1)
                ELSE do.extras
            END,
            CASE
                WHEN INSTR(do.extras, ',') > 0 THEN SUBSTR(do.extras, INSTR(do.extras, ',') + 1)
                ELSE ''
            END
        FROM delivered_orders AS do
        WHERE
            do.extras IS NOT NULL AND do.extras != ''
        UNION ALL
        SELECT
            se.order_id,
            se.pizza_id,
            CASE
                WHEN INSTR(se.rest, ',') > 0 THEN SUBSTR(se.rest, 1, INSTR(se.rest, ',') - 1)
                ELSE se.rest
            END,
            CASE
                WHEN INSTR(se.rest, ',') > 0 THEN SUBSTR(se.rest, INSTR(se.rest, ',') + 1)
                ELSE ''
            END
        FROM sx_rec AS se
        WHERE
            se.rest != ''
    )
    SELECT
        order_id,
        pizza_id,
        CAST(topping_id_str AS INTEGER) AS topping_id
    FROM sx_rec
    WHERE
        topping_id_str != ''
),
all_topping_changes AS (
    -- Base toppings for delivered pizzas
    SELECT
        do.order_id,
        do.pizza_id,
        sr.topping_id,
        1 AS quantity_change
    FROM delivered_orders AS do
    JOIN split_recipes AS sr
        ON do.pizza_id = sr.pizza_id

    UNION ALL

    -- Excluded toppings for delivered pizzas
    SELECT
        se.order_id,
        se.pizza_id,
        se.topping_id,
        -1 AS quantity_change
    FROM split_exclusions AS se

    UNION ALL

    -- Extra toppings for delivered pizzas
    SELECT
        sx.order_id,
        sx.pizza_id,
        sx.topping_id,
        1 AS quantity_change
    FROM split_extras AS sx
)
SELECT
    pt.topping_name,
    SUM(atc.quantity_change) AS total_quantity
FROM all_topping_changes AS atc
JOIN main.pizza_toppings AS pt
    ON atc.topping_id = pt.topping_id
GROUP BY
    pt.topping_name
ORDER BY
    total_quantity DESC