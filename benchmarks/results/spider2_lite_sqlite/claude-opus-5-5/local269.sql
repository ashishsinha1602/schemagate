WITH RECURSIVE roots AS (
  SELECT p.id
  FROM packaging p
  WHERE p.id NOT IN (SELECT contains_id FROM packaging_relations)
),
expanded AS (
  SELECT r.id AS root_id,
         pr.contains_id AS item_id,
         pr.qty AS qty
  FROM roots r
  JOIN packaging_relations pr ON pr.packaging_id = r.id
  UNION ALL
  SELECT e.root_id,
         pr.contains_id,
         e.qty * pr.qty
  FROM expanded e
  JOIN packaging_relations pr ON pr.packaging_id = e.item_id
),
leaf_totals AS (
  SELECT e.root_id,
         SUM(e.qty) AS total_qty
  FROM expanded e
  WHERE e.item_id NOT IN (SELECT packaging_id FROM packaging_relations)
  GROUP BY e.root_id
)
SELECT AVG(total_qty) AS avg_total_qty
FROM leaf_totals