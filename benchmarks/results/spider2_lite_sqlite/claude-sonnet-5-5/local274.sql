SELECT p.id AS product_id, p.name AS product_name, AVG(pl.qty) AS avg_qty_picked
FROM picking_line pl
JOIN products p ON p.id = pl.product_id
WHERE pl.order_id = 421
GROUP BY p.id, p.name