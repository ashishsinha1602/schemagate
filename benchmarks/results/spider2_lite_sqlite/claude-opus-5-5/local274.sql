SELECT p.id AS product_id,
       p.name AS product_name,
       AVG(pl.qty) AS avg_units_picked
FROM picking_line pl
JOIN products p ON p.id = pl.product_id
JOIN picking_list pk ON pk.id = pl.picklist_id
WHERE pl.order_id = 421
GROUP BY p.id, p.name
ORDER BY MIN(pk.created), MIN(pl.picklist_id), MIN(pl.line_no)