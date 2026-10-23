WITH ProductEvents AS (
    SELECT
        sph.product_id,
        sce.visit_id,
        sce.event_type
    FROM
        main.shopping_cart_events AS sce
    JOIN
        main.shopping_cart_page_hierarchy AS sph
        ON sce.page_id = sph.page_id
    WHERE
        sce.page_id NOT IN (1, 2, 12, 13)
),
AddedToCartVisits AS (
    SELECT DISTINCT
        visit_id,
        product_id
    FROM
        ProductEvents
    WHERE
        event_type = 2 -- Add to cart
),
PurchasedVisits AS (
    SELECT DISTINCT
        visit_id,
        product_id
    FROM
        ProductEvents
    WHERE
        event_type = 3 -- Purchase
),
LeftInCartCounts AS (
    SELECT
        a.product_id,
        COUNT(*) AS times_left_in_cart
    FROM
        AddedToCartVisits AS a
    LEFT JOIN
        PurchasedVisits AS p
        ON a.visit_id = p.visit_id AND a.product_id = p.product_id
    WHERE
        p.visit_id IS NULL -- Was added but not purchased in that visit
    GROUP BY
        a.product_id
)
SELECT
    pe.product_id,
    SUM(CASE WHEN pe.event_type = 1 THEN 1 ELSE 0 END) AS times_viewed,
    SUM(CASE WHEN pe.event_type = 2 THEN 1 ELSE 0 END) AS times_added_to_cart,
    COALESCE(lic.times_left_in_cart, 0) AS times_left_in_cart,
    SUM(CASE WHEN pe.event_type = 3 THEN 1 ELSE 0 END) AS actual_purchases
FROM
    ProductEvents AS pe
LEFT JOIN
    LeftInCartCounts AS lic
    ON pe.product_id = lic.product_id
GROUP BY
    pe.product_id