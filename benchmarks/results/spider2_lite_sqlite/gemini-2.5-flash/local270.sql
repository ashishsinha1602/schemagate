WITH RECURSIVE packaging_path AS (
    -- Anchor member: Direct contents of a packaging
    SELECT
        pr.packaging_id AS root_packaging_id,
        pr.contains_id AS contained_item_id,
        pr.qty AS accumulated_qty
    FROM main.packaging_relations pr

    UNION ALL

    -- Recursive member: Nested contents
    -- Join with packaging_relations to find what the current contained_item_id itself contains
    SELECT
        pp.root_packaging_id,
        pr.contains_id AS contained_item_id,
        pp.accumulated_qty * pr.qty AS accumulated_qty
    FROM packaging_path pp
    JOIN main.packaging_relations pr ON pp.contained_item_id = pr.packaging_id
),
top_level_containers AS (
    -- Identify packaging items that are not contained by any other packaging
    SELECT p.id
    FROM main.packaging p
    LEFT JOIN main.packaging_relations pr_contained_by ON p.id = pr_contained_by.contains_id
    WHERE pr_contained_by.contains_id IS NULL
)
SELECT
    p_container.name AS container_name,
    p_item.name AS item_name
FROM packaging_path pp
JOIN top_level_containers tlc ON pp.root_packaging_id = tlc.id
JOIN main.packaging p_container ON tlc.id = p_container.id
JOIN main.packaging p_item ON pp.contained_item_id = p_item.id
GROUP BY p_container.id, p_item.id -- Group by IDs to ensure unique container/item pairs
HAVING SUM(pp.accumulated_qty) > 500