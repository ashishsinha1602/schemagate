WITH orders AS (
  SELECT ROW_NUMBER() OVER (ORDER BY order_id, order_time, pizza_id) AS row_id,
         order_id, customer_id, pizza_id,
         COALESCE(exclusions, '') AS exclusions,
         COALESCE(extras, '') AS extras,
         order_time
  FROM pizza_clean_customer_orders
),
split_recipe(pizza_id, item, rest) AS (
  SELECT pizza_id, '', toppings || ',' FROM pizza_recipes
  UNION ALL
  SELECT pizza_id,
         TRIM(SUBSTR(rest, 1, INSTR(rest, ',') - 1)),
         SUBSTR(rest, INSTR(rest, ',') + 1)
  FROM split_recipe WHERE rest <> ''
),
split_excl(row_id, item, rest) AS (
  SELECT row_id, '', exclusions || ',' FROM orders
  UNION ALL
  SELECT row_id,
         TRIM(SUBSTR(rest, 1, INSTR(rest, ',') - 1)),
         SUBSTR(rest, INSTR(rest, ',') + 1)
  FROM split_excl WHERE rest <> ''
),
split_extra(row_id, item, rest) AS (
  SELECT row_id, '', extras || ',' FROM orders
  UNION ALL
  SELECT row_id,
         TRIM(SUBSTR(rest, 1, INSTR(rest, ',') - 1)),
         SUBSTR(rest, INSTR(rest, ',') + 1)
  FROM split_extra WHERE rest <> ''
),
excl AS (
  SELECT row_id, CAST(item AS INTEGER) AS topping_id
  FROM split_excl WHERE item <> '' AND item <> 'null'
),
extra AS (
  SELECT row_id, CAST(item AS INTEGER) AS topping_id
  FROM split_extra WHERE item <> '' AND item <> 'null'
),
all_ing AS (
  SELECT o.row_id, CAST(r.item AS INTEGER) AS topping_id
  FROM orders o
  JOIN split_recipe r ON r.pizza_id = o.pizza_id AND r.item <> ''
  WHERE NOT EXISTS (
    SELECT 1 FROM excl e
    WHERE e.row_id = o.row_id AND e.topping_id = CAST(r.item AS INTEGER)
  )
  UNION ALL
  SELECT row_id, topping_id FROM extra
),
ing_counts AS (
  SELECT a.row_id, t.topping_name, COUNT(*) AS cnt
  FROM all_ing a
  JOIN pizza_toppings t ON t.topping_id = a.topping_id
  GROUP BY a.row_id, t.topping_name
),
agg AS (
  SELECT row_id, GROUP_CONCAT(label, ', ') AS ing
  FROM (
    SELECT row_id,
           CASE WHEN cnt > 1 THEN cnt || 'x' || topping_name ELSE topping_name END AS label,
           CASE WHEN cnt > 1 THEN 0 ELSE 1 END AS grp,
           topping_name
    FROM ing_counts
    ORDER BY row_id, grp, topping_name
  )
  GROUP BY row_id
)
SELECT o.row_id,
       o.order_id,
       o.customer_id,
       n.pizza_name,
       n.pizza_name || ': ' || COALESCE(a.ing, '') AS ingredients
FROM orders o
JOIN pizza_names n ON n.pizza_id = o.pizza_id
LEFT JOIN agg a ON a.row_id = o.row_id
GROUP BY o.row_id, o.order_id, n.pizza_name, o.order_time
ORDER BY o.row_id ASC