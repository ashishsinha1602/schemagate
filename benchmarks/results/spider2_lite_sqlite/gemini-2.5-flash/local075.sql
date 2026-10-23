WITH ProductEvents AS (
    SELECT
        sph.product_id,
        sce.visit_id,
        scei.event_name,
        sce.event_type
    FROM
        main.shopping_cart_events AS sce
    JOIN
        main.shopping_cart_page_hierarchy AS sph
        ON sce.page_id = sph.page_id
    JOIN
        main.shopping_cart_event_identifier AS scei
        ON sce.event_type = scei.event_type
    WHERE
        sph.page_id NOT IN (1, 2, 12, 13)
        AND sph.product_id IS NOT NULL
),
ProductEventCounts AS (
    SELECT
        product_id,
        SUM(CASE WHEN event_name = 'Page View' THEN 1 ELSE 0 END) AS product_views,
        SUM(CASE WHEN event_name = 'Add to Cart' THEN 1 ELSE 0 END) AS added_to_cart,
        SUM(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) AS actual_purchases
    FROM
        ProductEvents
    GROUP BY
        product_id
),
VisitProductSummary AS (
    SELECT
        product_id,
        visit_id,
        MAX(CASE WHEN event_name = 'Add to Cart' THEN 1 ELSE 0 END) AS added_to_cart_in_visit,
        MAX(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) AS purchased_in_visit,
        MAX(CASE WHEN event_name = 'Remove from Cart' THEN 1 ELSE 0 END) AS removed_from_cart_in_visit
    FROM
        ProductEvents
    GROUP BY
        product_id,
        visit_id
),
LeftInCartCounts AS (
    SELECT
        product_id,
        SUM(CASE WHEN added_to_cart_in_visit = 1 AND purchased_in_visit = 0 AND removed_from_cart_in_visit = 0 THEN 1 ELSE 0 END) AS left_in_cart
    FROM
        VisitProductSummary
    GROUP BY
        product_id
)
SELECT
    pec.product_id,
    pec.product_views,
    pec.added_to_cart,
    pec.actual_purchases,
    COALESCE(lic.left_in_cart, 0) AS left_in_cart
FROM
    ProductEventCounts AS pec
LEFT JOIN
    LeftInCartCounts AS lic
    ON pec.product_id = lic.product_id
ORDER BY
    pec.product_id