WITH RECURSIVE orders AS (
  SELECT ROW_NUMBER() OVER () AS rid, c.pizza_id, c.exclusions, c.extras
  FROM pizza_clean_customer_orders c
  JOIN pizza_clean_runner_orders r ON c.order_id = r.order_id
  WHERE r.cancellation IS NULL OR r.cancellation = ''
),
src AS (
  SELECT o.rid, 'base' AS kind, p.toppings AS s
  FROM orders o JOIN pizza_recipes p ON o.pizza_id = p.pizza_id
  UNION ALL
  SELECT rid, 'extra', extras FROM orders WHERE extras IS NOT NULL AND extras <> ''
  UNION ALL
  SELECT rid, 'excl', exclusions FROM orders WHERE exclusions IS NOT NULL AND exclusions <> ''
),
split(rid, kind, item, rest) AS (
  SELECT rid, kind, '', s || ',' FROM src
  UNION ALL
  SELECT rid, kind,
         TRIM(substr(rest, 1, instr(rest, ',') - 1)),
         substr(rest, instr(rest, ',') + 1)
  FROM split WHERE rest <> ''
),
items AS (
  SELECT rid, kind, CAST(item AS INTEGER) AS tid
  FROM split WHERE TRIM(item) <> ''
),
per_pizza AS (
  SELECT rid, tid,
         MAX(0, SUM(CASE WHEN kind = 'excl' THEN -1 ELSE 1 END)) AS qty
  FROM items
  GROUP BY rid, tid
)
SELECT t.topping_name AS ingredient, SUM(pp.qty) AS quantity
FROM per_pizza pp
JOIN pizza_toppings t ON t.topping_id = pp.tid
GROUP BY t.topping_name
ORDER BY quantity DESC, t.topping_name