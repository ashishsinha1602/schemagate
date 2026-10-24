WITH RECURSIVE tree(root_id, item_id, qty) AS (
  SELECT pr.packaging_id, pr.contains_id, pr.qty
  FROM packaging_relations pr
  WHERE pr.packaging_id NOT IN (SELECT contains_id FROM packaging_relations)
  UNION ALL
  SELECT t.root_id, pr.contains_id, t.qty * pr.qty
  FROM tree t
  JOIN packaging_relations pr ON pr.packaging_id = t.item_id
),
totals AS (
  SELECT root_id, item_id, SUM(qty) AS total_qty
  FROM tree
  GROUP BY root_id, item_id
)
SELECT p1.name AS container_name, p2.name AS item_name, tt.total_qty
FROM totals tt
JOIN packaging p1 ON p1.id = tt.root_id
JOIN packaging p2 ON p2.id = tt.item_id
WHERE tt.total_qty > 500
ORDER BY p1.name, p2.name