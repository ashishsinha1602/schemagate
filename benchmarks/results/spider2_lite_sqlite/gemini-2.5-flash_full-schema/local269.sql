WITH RECURSIVE ExpandedPackaging AS (
  -- Base case: direct relations from a packaging item to what it directly contains
  SELECT
    pr.packaging_id AS top_packaging_id,
    pr.contains_id AS contained_item_id,
    pr.qty AS quantity
  FROM main.packaging_relations AS pr

  UNION ALL

  -- Recursive step: expand nested relations
  -- Join the current expanded path with further packaging relations
  -- to find items contained deeper in the hierarchy.
  -- Multiply quantities along the path.
  SELECT
    ep.top_packaging_id,
    pr.contains_id AS contained_item_id,
    ep.quantity * pr.qty AS quantity
  FROM ExpandedPackaging AS ep
  JOIN main.packaging_relations AS pr
    ON ep.contained_item_id = pr.packaging_id
),
LeafItems AS (
  -- Identify packaging items that do not contain any other items.
  -- These are the "leaf-level items" in the hierarchy.
  SELECT id
  FROM main.packaging
  WHERE id NOT IN (SELECT packaging_id FROM main.packaging_relations)
),
CalculatedContainerTotals AS (
  -- For each top-level packaging item that is a container,
  -- sum the quantities of all leaf-level items it ultimately contains.
  SELECT
    ep.top_packaging_id,
    SUM(ep.quantity) AS TotalLeafQty
  FROM ExpandedPackaging AS ep
  JOIN LeafItems AS li
    ON ep.contained_item_id = li.id
  GROUP BY
    ep.top_packaging_id
),
AllPackagingTotals AS (
  -- Determine the total leaf quantity for every packaging item.
  -- 1. If a packaging item is a leaf itself, its total leaf quantity is 1 (itself).
  -- 2. If a packaging item is a container and contains leaf items, use the calculated sum.
  -- 3. If a packaging item is a container but ultimately contains no leaf items, its total leaf quantity is 0.
  SELECT
    p.id AS packaging_id,
    CASE
      WHEN p.id IN (SELECT id FROM LeafItems) THEN 1
      WHEN cct.TotalLeafQty IS NOT NULL THEN cct.TotalLeafQty
      ELSE 0
    END AS FinalTotalQty
  FROM main.packaging AS p
  LEFT JOIN CalculatedContainerTotals AS cct
    ON p.id = cct.top_packaging_id
)
-- Calculate the average of these total leaf quantities across all packaging combinations.
SELECT
  AVG(FinalTotalQty)
FROM AllPackagingTotals