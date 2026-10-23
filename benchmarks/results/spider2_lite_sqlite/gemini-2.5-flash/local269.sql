WITH RECURSIVE ExpandedPackaging AS (
    -- Base case: direct contents of a packaging item
    SELECT
        pr.packaging_id AS top_packaging_id,
        pr.contains_id AS contained_packaging_id,
        pr.qty AS effective_qty
    FROM
        main.packaging_relations AS pr

    UNION ALL

    -- Recursive step: expand contents of contained packaging items
    SELECT
        ep.top_packaging_id,
        pr_next.contains_id AS contained_packaging_id,
        ep.effective_qty * pr_next.qty AS effective_qty
    FROM
        ExpandedPackaging AS ep
    JOIN
        main.packaging_relations AS pr_next
        ON ep.contained_packaging_id = pr_next.packaging_id
),
LeafItems AS (
    -- Identify packaging items that do not contain other packaging items
    SELECT
        p.id
    FROM
        main.packaging AS p
    LEFT JOIN
        main.packaging_relations AS pr_container
        ON p.id = pr_container.packaging_id
    WHERE
        pr_container.packaging_id IS NULL
)
SELECT
    AVG(TotalLeafQty.sum_leaf_qty)
FROM (
    -- For each top-level packaging, sum the effective quantities of its leaf-level contents
    SELECT
        ep.top_packaging_id,
        SUM(ep.effective_qty) AS sum_leaf_qty
    FROM
        ExpandedPackaging AS ep
    JOIN
        LeafItems AS li
        ON ep.contained_packaging_id = li.id
    GROUP BY
        ep.top_packaging_id
) AS TotalLeafQty