WITH RECURSIVE o AS (
  SELECT rowid AS row_id, order_id, customer_id, pizza_id, exclusions, extras, order_time
  FROM pizza_clean_customer_orders
),
src AS (
  SELECT o.row_id, 'std' AS kind, r.toppings || ',' AS s
  FROM o JOIN pizza_recipes r ON r.pizza_id = o.pizza_id
  UNION ALL
  SELECT row_id, 'exc', exclusions || ','
  FROM o
  WHERE exclusions IS NOT NULL AND trim(exclusions) <> '' AND lower(trim(exclusions)) <> 'null'
  UNION ALL
  SELECT row_id, 'ext', extras || ','
  FROM o
  WHERE extras IS NOT NULL AND trim(extras) <> '' AND lower(trim(extras)) <> 'null'
),
split(row_id, kind, item, rest) AS (
  SELECT row_id, kind, trim(substr(s, 1, instr(s, ',') - 1)), substr(s, instr(s, ',') + 1) FROM src
  UNION ALL
  SELECT row_id, kind, trim(substr(rest, 1, instr(rest, ',') - 1)), substr(rest, instr(rest, ',') + 1)
  FROM split WHERE rest <> ''
),
items AS (
  SELECT row_id, kind, CAST(item AS INTEGER) AS tid
  FROM split WHERE item <> ''
),
final_items AS (
  SELECT row_id, tid FROM items s
  WHERE kind = 'std'
    AND NOT EXISTS (SELECT 1 FROM items e WHERE e.row_id = s.row_id AND e.kind = 'exc' AND e.tid = s.tid)
  UNION ALL
  SELECT row_id, tid FROM items WHERE kind = 'ext'
),
counted AS (
  SELECT f.row_id, t.topping_name AS name, COUNT(*) AS cnt
  FROM final_items f JOIN pizza_toppings t ON t.topping_id = f.tid
  GROUP BY f.row_id, t.topping_name
),
ordered AS (
  SELECT row_id,
         CASE WHEN cnt > 1 THEN cnt || 'x' || name ELSE name END AS label
  FROM counted
  ORDER BY row_id, cnt DESC, name
),
ing AS (
  SELECT row_id, group_concat(label, ', ') AS ingredients
  FROM ordered
  GROUP BY row_id
)
SELECT o.row_id, o.order_id, o.customer_id, n.pizza_name,
       n.pizza_name || ': ' || COALESCE(i.ingredients, '') AS final_ingredients
FROM o
JOIN pizza_names n ON n.pizza_id = o.pizza_id
LEFT JOIN ing i ON i.row_id = o.row_id
GROUP BY o.row_id, o.order_id, o.customer_id, n.pizza_name, o.order_time
ORDER BY o.row_id ASC