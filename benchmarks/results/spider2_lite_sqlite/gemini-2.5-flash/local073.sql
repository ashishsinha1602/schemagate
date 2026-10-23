WITH RECURSIVE split_recipe_toppings(pizza_id, topping_id_str, rest) AS (
    SELECT
        pizza_id,
        CASE
            WHEN INSTR(toppings, ',') > 0 THEN SUBSTR(toppings, 1, INSTR(toppings, ',') - 1)
            ELSE toppings
        END,
        CASE
            WHEN INSTR(toppings, ',') > 0 THEN SUBSTR(toppings, INSTR(toppings, ',') + 1)
            ELSE ''
        END
    FROM main.pizza_recipes
    UNION ALL
    SELECT
        pizza_id,
        CASE
            WHEN INSTR(rest, ',') > 0 THEN SUBSTR(rest, 1, INSTR(rest, ',') - 1)
            ELSE rest
        END,
        CASE
            WHEN INSTR(rest, ',') > 0 THEN SUBSTR(rest, INSTR(rest, ',') + 1)
            ELSE ''
        END
    FROM split_recipe_toppings
    WHERE rest != ''
),
standard_toppings_unnested AS (
    SELECT
        srt.pizza_id,
        CAST(TRIM(srt.topping_id_str) AS INTEGER) AS topping_id,
        pt.topping_name
    FROM split_recipe_toppings srt
    JOIN main.pizza_toppings pt ON CAST(TRIM(srt.topping_id_str) AS INTEGER) = pt.topping_id
),
base_pizza_info AS (
    SELECT
        pco.rowid AS pizza_order_row_id,
        pco.order_id,
        pco.customer_id,
        pco.pizza_id,
        pn.pizza_name,
        pco.order_time
    FROM main.pizza_customer_orders pco
    JOIN main.pizza_names pn ON pco.pizza_id = pn.pizza_id
),
excluded_toppings_per_order AS (
    SELECT
        pge.row_id AS pizza_order_row_id,
        pge.exclusions AS topping_id
    FROM main.pizza_get_exclusions pge
),
extra_toppings_per_order AS (
    SELECT
        pge.row_id AS pizza_order_row_id,
        pge.extras AS topping_id,
        pt.topping_name
    FROM main.pizza_get_extras pge
    JOIN main.pizza_toppings pt ON pge.extras = pt.topping_id
),
all_potential_ingredients AS (
    -- Standard toppings, excluding those explicitly excluded for this order item
    SELECT
        bpi.pizza_order_row_id,
        bpi.order_id,
        bpi.customer_id,
        bpi.pizza_name,
        bpi.order_time,
        stu.topping_name AS ingredient_name
    FROM base_pizza_info bpi
    JOIN standard_toppings_unnested stu ON bpi.pizza_id = stu.pizza_id
    LEFT JOIN excluded_toppings_per_order etpo
        ON bpi.pizza_order_row_id = etpo.pizza_order_row_id
        AND stu.topping_id = etpo.topping_id
    WHERE etpo.topping_id IS NULL -- Only include if NOT excluded

    UNION ALL

    -- Extra toppings
    SELECT
        bpi.pizza_order_row_id,
        bpi.order_id,
        bpi.customer_id,
        bpi.pizza_name,
        bpi.order_time,
        etpo.topping_name AS ingredient_name
    FROM base_pizza_info bpi
    JOIN extra_toppings_per_order etpo ON bpi.pizza_order_row_id = etpo.pizza_order_row_id
),
counted_ingredients AS (
    SELECT
        pizza_order_row_id,
        order_id,
        customer_id,
        pizza_name,
        order_time,
        ingredient_name,
        COUNT(ingredient_name) AS ingredient_count
    FROM all_potential_ingredients
    GROUP BY
        pizza_order_row_id,
        order_id,
        customer_id,
        pizza_name,
        order_time,
        ingredient_name
),
ordered_formatted_ingredients AS (
    SELECT
        pizza_order_row_id,
        order_id,
        customer_id,
        pizza_name,
        order_time,
        CASE
            WHEN ingredient_count > 1 THEN '2x ' || ingredient_name
            ELSE ingredient_name
        END AS formatted_ingredient,
        ingredient_count,
        ingredient_name -- Used for secondary sort within counts
    FROM counted_ingredients
    ORDER BY
        pizza_order_row_id,
        ingredient_count DESC,
        ingredient_name ASC
)
SELECT
    ofi.pizza_order_row_id AS row_id,
    ofi.order_id,
    ofi.customer_id,
    ofi.pizza_name,
    ofi.pizza_name || ': ' || GROUP_CONCAT(ofi.formatted_ingredient, ', ') AS final_ingredients
FROM ordered_formatted_ingredients ofi
GROUP BY
    ofi.pizza_order_row_id,
    ofi.order_id,
    ofi.customer_id,
    ofi.pizza_name,
    ofi.order_time
ORDER BY
    ofi.pizza_order_row_id ASC