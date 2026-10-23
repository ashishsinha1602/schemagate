WITH RECURSIVE packaging_hierarchy AS (
    -- Anchor member: Direct contents of top-level packages
    SELECT
        pr.packaging_id AS top_level_packaging_id,
        pr.contains_id AS contained_product_id,
        pr.qty AS total_qty_multiplier
    FROM main.packaging_relations AS pr
    WHERE pr.packaging_id NOT IN (SELECT contains_id FROM main.packaging_relations)

    UNION ALL

    -- Recursive member: Traverse deeper into the hierarchy
    SELECT
        ph.top_level_packaging_id,
        pr.contains_id AS contained_product_id,
        ph.total_qty_multiplier * pr.qty AS total_qty_multiplier
    FROM packaging_hierarchy AS ph
    JOIN main.packaging_relations AS pr
        ON ph.contained_product_id = pr.packaging_id
)
SELECT
    p_top.name AS top_level_container_name,
    p_item.name AS contained_item_name
FROM packaging_hierarchy AS ph
JOIN main.packaging AS p_top
    ON ph.top_level_packaging_id = p_top.id
JOIN main.packaging AS p_item
    ON ph.contained_product_id = p_item.id
GROUP BY
    p_top.name,
    p_item.name
HAVING SUM(ph.total_qty_multiplier) > 500