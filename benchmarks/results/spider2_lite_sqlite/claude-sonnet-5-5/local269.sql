WITH RECURSIVE exp(root_id, item_id, qty) AS (
  SELECT pr.packaging_id, pr.contains_id, pr.qty
  FROM packaging_relations pr
  WHERE pr.packaging_id NOT IN (SELECT contains_id FROM packaging_relations)
  UNION ALL
  SELECT e.root_id, pr.contains_id, e.qty * pr.qty
  FROM exp e
  JOIN packaging_relations pr ON pr.packaging_id = e.item_id
),
totals AS (
  SELECT root_id, SUM(qty) AS total_qty
  FROM exp
  WHERE item_id NOT IN (SELECT packaging_id FROM packaging_relations)
  GROUP BY root_id
)
SELECT AVG(total_qty) AS avg_total_qty
FROM totals