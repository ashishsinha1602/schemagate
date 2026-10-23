WITH RECURSIVE tree(root_id, item_id, qty) AS (
  SELECT pr.packaging_id, pr.contains_id, pr.qty
  FROM packaging_relations pr
  WHERE pr.packaging_id NOT IN (SELECT contains_id FROM packaging_relations)
  UNION ALL
  SELECT t.root_id, pr.contains_id, t.qty * pr.qty
  FROM tree t
  JOIN packaging_relations pr ON pr.packaging_id = t.item_id
)
SELECT p.name AS container_name, i.name AS item_name
FROM (
  SELECT root_id, item_id, SUM(qty) AS total_qty
  FROM tree
  WHERE item_id NOT IN (SELECT packaging_id FROM packaging_relations)
  GROUP BY root_id, item_id
  HAVING SUM(qty) > 500
) x
JOIN packaging p ON p.id = x.root_id
JOIN packaging i ON i.id = x.item_id