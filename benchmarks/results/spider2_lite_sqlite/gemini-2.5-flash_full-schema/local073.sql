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
base_toppings_parsed AS (
    SELECT
        srt.pizza_id,
        CAST(TRIM(srt.topping_id_str) AS INTEGER) AS topping_id,
        pt.topping_name
    FROM split_recipe_toppings srt
    JOIN main.pizza_toppings pt ON CAST(TRIM(srt.topping_id_str) AS INTEGER) = pt.topping_id
    WHERE srt.topping_id_str != ''
),
order_details AS (
    SELECT
        pco.ROWID AS row_id,
        pco.order_id,
        pco.customer_id,
        pco.pizza_id,
        pn.pizza_name,
        pco.order_time
    FROM main.pizza_customer_orders pco
    JOIN main.pizza_names pn ON pco.pizza_id = pn.pizza_id
),
base_ingredients_for_order AS (
    SELECT
        od.row_id,
        od.order_id,
        od.customer_id,
        od.pizza_name,
        od.order_time,
        btp.topping_name AS ingredient
    FROM order_details od
    JOIN base_toppings_parsed btp ON od.pizza_id = btp.pizza_id
),
excluded_ingredients_for_order AS (
    SELECT
        pge.row_id,
        pge.order_id,
        pt.topping_name AS ingredient
    FROM main.pizza_get_exclusions pge
    JOIN main.pizza_toppings pt ON pge.exclusions = pt.topping_id
),
extra_ingredients_for_order AS (
    SELECT
        pge.row_id,
        pge.order_id,
        pt.topping_name AS ingredient
    FROM main.pizza_get_extras pge
    JOIN main.pizza_toppings pt ON pge.extras = pt.topping_id
),
ingredients_after_exclusions AS (
    SELECT
        bio.row_id,
        bio.order_id,
        bio.customer_id,
        bio.pizza_name,
        bio.order_time,
        bio.ingredient
    FROM base_ingredients_for_order bio
    LEFT JOIN excluded_ingredients_for_order eio
        ON bio.row_id = eio.row_id
       AND bio.order_id = eio.order_id
       AND bio.ingredient = eio.ingredient
    WHERE eio.ingredient IS NULL
),
final_ingredients_raw AS (
    SELECT
        iae.row_id,
        iae.order_id,
        iae.customer_id,
        iae.pizza_name,
        iae.order_time,
        iae.ingredient
    FROM ingredients_after_exclusions iae

    UNION ALL

    SELECT
        eio.row_id,
        od.order_id,
        od.customer_id,
        od.pizza_name,
        od.order_time,
        eio.ingredient
    FROM extra_ingredients_for_order eio
    JOIN order_details od ON eio.row_id = od.row_id AND eio.order_id = od.order_id
),
final_ingredients_counted AS (
    SELECT
        fir.row_id,
        fir.order_id,
        fir.customer_id,
        fir.pizza_name,
        fir.order_time,
        fir.ingredient,
        COUNT(*) AS ingredient_count
    FROM final_ingredients_raw fir
    GROUP BY
        fir.row_id,
        fir.order_id,
        fir.customer_id,
        fir.pizza_name,
        fir.order_time,
        fir.ingredient
)
SELECT
    fic.row_id,
    fic.order_id,
    fic.customer_id,
    fic.pizza_name,
    fic.pizza_name || ': ' || GROUP_CONCAT(
        CASE
            WHEN fic.ingredient_count > 1 THEN CAST(fic.ingredient_count AS TEXT) || 'x ' || fic.ingredient
            ELSE fic.ingredient
        END, ', '
        ORDER BY
            CASE WHEN fic.ingredient_count > 1 THEN 0 ELSE 1 END,
            fic.ingredient
    ) AS final_ingredients
FROM final_ingredients_counted fic
GROUP BY
    fic.row_id,
    fic.order_id,
    fic.customer_id,
    fic.pizza_name,
    fic.order_time
ORDER BY
    fic.row_id