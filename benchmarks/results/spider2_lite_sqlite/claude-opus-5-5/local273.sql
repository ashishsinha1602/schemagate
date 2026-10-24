WITH ol AS (
  SELECT customer_id, ordered, product_id, product_name, SUM(qty) AS qty
  FROM customer_order_products
  GROUP BY customer_id, ordered, product_id, product_name
),
olc AS (
  SELECT customer_id, ordered, product_id, product_name, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY ordered, customer_id ROWS UNBOUNDED PRECEDING) - qty AS o_from,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY ordered, customer_id ROWS UNBOUNDED PRECEDING) AS o_to
  FROM ol
),
inv AS (
  SELECT id, product_id, location_id, purchased, qty,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY purchased, qty, id ROWS UNBOUNDED PRECEDING) - qty AS i_from,
         SUM(qty) OVER (PARTITION BY product_id ORDER BY purchased, qty, id ROWS UNBOUNDED PRECEDING) AS i_to
  FROM inventory_with_dims
),
picks AS (
  SELECT olc.product_name,
         olc.qty AS order_qty,
         MIN(olc.o_to, inv.i_to) - MAX(olc.o_from, inv.i_from) AS picked
  FROM olc
  JOIN inv
    ON inv.product_id = olc.product_id
   AND inv.i_from < olc.o_to
   AND inv.i_to > olc.o_from
)
SELECT product_name,
       AVG(picked * 1.0 / order_qty) AS avg_pick_percentage
FROM picks
GROUP BY product_name
ORDER BY product_name