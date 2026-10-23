WITH SellerOverallSales AS (
    SELECT
        oi.seller_id,
        SUM(oi.price) AS total_sales,
        AVG(oi.price) AS avg_item_price,
        COUNT(oi.order_item_id) AS total_products_sold
    FROM
        main.order_items AS oi
    GROUP BY
        oi.seller_id
    HAVING
        COUNT(oi.order_item_id) > 100
),
SellerReviews AS (
    SELECT
        oi.seller_id,
        AVG(orr.review_score) AS avg_review_score
    FROM
        main.order_items AS oi
    JOIN
        main.orders AS o ON oi.order_id = o.order_id
    JOIN
        main.order_reviews AS orr ON o.order_id = orr.order_id
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerOverallSales)
    GROUP BY
        oi.seller_id
),
SellerPackingTimes AS (
    SELECT
        oi.seller_id,
        AVG(
            (JULIANDAY(o.order_delivered_carrier_date) - JULIANDAY(COALESCE(o.order_approved_at, o.order_purchase_timestamp))) * 24
        ) AS avg_packing_hours
    FROM
        main.order_items AS oi
    JOIN
        main.orders AS o ON oi.order_id = o.order_id
    WHERE
        o.order_delivered_carrier_date IS NOT NULL
        AND COALESCE(o.order_approved_at, o.order_purchase_timestamp) IS NOT NULL
        AND oi.seller_id IN (SELECT seller_id FROM SellerOverallSales)
    GROUP BY
        oi.seller_id
),
SellerCategorySalesRanked AS (
    SELECT
        oi.seller_id,
        COALESCE(pct.product_category_name_english, 'unknown') AS product_category_name_english,
        SUM(oi.price) AS category_total_sales,
        AVG(oi.price) AS category_avg_item_price,
        ROW_NUMBER() OVER (PARTITION BY oi.seller_id ORDER BY SUM(oi.price) DESC, COALESCE(pct.product_category_name_english, 'unknown') ASC) AS rn
    FROM
        main.order_items AS oi
    JOIN
        main.products AS p ON oi.product_id = p.product_id
    LEFT JOIN
        main.product_category_name_translation AS pct ON p.product_category_name = pct.product_category_name
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerOverallSales)
    GROUP BY
        oi.seller_id,
        COALESCE(pct.product_category_name_english, 'unknown')
)
SELECT
    s.seller_id,
    s.seller_city,
    s.seller_state,
    sos.total_products_sold,
    sos.total_sales,
    sos.avg_item_price,
    sr.avg_review_score,
    spt.avg_packing_hours,
    scsr.product_category_name_english AS top_selling_category_english,
    scsr.category_total_sales AS top_category_sales_volume,
    scsr.category_avg_item_price AS top_category_avg_item_price
FROM
    main.sellers AS s
JOIN
    SellerOverallSales AS sos ON s.seller_id = sos.seller_id
LEFT JOIN
    SellerReviews AS sr ON s.seller_id = sr.seller_id
LEFT JOIN
    SellerPackingTimes AS spt ON s.seller_id = spt.seller_id
LEFT JOIN
    SellerCategorySalesRanked AS scsr ON s.seller_id = scsr.seller_id AND scsr.rn = 1
ORDER BY
    sos.total_sales DESC