WITH SellerProductCounts AS (
    SELECT
        oi.seller_id,
        COUNT(oi.order_item_id) AS products_sold_count
    FROM
        main.order_items AS oi
    GROUP BY
        oi.seller_id
    HAVING
        COUNT(oi.order_item_id) > 100
),
SellerSalesMetrics AS (
    SELECT
        oi.seller_id,
        SUM(oi.price + oi.freight_value) AS total_sales,
        AVG(oi.price) AS average_item_price
    FROM
        main.order_items AS oi
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerProductCounts)
    GROUP BY
        oi.seller_id
),
SellerOrderReviews AS (
    SELECT DISTINCT
        oi.seller_id,
        o.order_id,
        orv.review_score
    FROM
        main.order_items AS oi
    JOIN
        main.orders AS o
        ON oi.order_id = o.order_id
    JOIN
        main.order_reviews AS orv
        ON o.order_id = orv.order_id
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerProductCounts)
),
SellerAvgReviewScores AS (
    SELECT
        seller_id,
        AVG(review_score) AS average_review_score
    FROM
        SellerOrderReviews
    GROUP BY
        seller_id
),
SellerOrderPackingTimes AS (
    SELECT DISTINCT
        oi.seller_id,
        o.order_id,
        o.order_approved_at,
        o.order_delivered_carrier_date
    FROM
        main.order_items AS oi
    JOIN
        main.orders AS o
        ON oi.order_id = o.order_id
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerProductCounts)
        AND o.order_approved_at IS NOT NULL
        AND o.order_delivered_carrier_date IS NOT NULL
),
SellerAvgPackingTimes AS (
    SELECT
        seller_id,
        AVG(julianday(order_delivered_carrier_date) - julianday(order_approved_at)) AS average_packing_time_days
    FROM
        SellerOrderPackingTimes
    GROUP BY
        seller_id
),
SellerCategorySales AS (
    SELECT
        oi.seller_id,
        pct.product_category_name_english,
        SUM(oi.price + oi.freight_value) AS category_sales_volume
    FROM
        main.order_items AS oi
    JOIN
        main.products AS p
        ON oi.product_id = p.product_id
    JOIN
        main.product_category_name_translation AS pct
        ON p.product_category_name = pct.product_category_name
    WHERE
        oi.seller_id IN (SELECT seller_id FROM SellerProductCounts)
    GROUP BY
        oi.seller_id,
        pct.product_category_name_english
),
RankedSellerCategorySales AS (
    SELECT
        seller_id,
        product_category_name_english,
        category_sales_volume,
        ROW_NUMBER() OVER (PARTITION BY seller_id ORDER BY category_sales_volume DESC, product_category_name_english ASC) AS rn
    FROM
        SellerCategorySales
)
SELECT
    s.seller_id,
    s.seller_city,
    s.seller_state,
    ssm.total_sales,
    ssm.average_item_price,
    sars.average_review_score,
    sapt.average_packing_time_days,
    rscs.product_category_name_english AS top_selling_category_english,
    spc.products_sold_count
FROM
    main.sellers AS s
JOIN
    SellerProductCounts AS spc
    ON s.seller_id = spc.seller_id
LEFT JOIN
    SellerSalesMetrics AS ssm
    ON s.seller_id = ssm.seller_id
LEFT JOIN
    SellerAvgReviewScores AS sars
    ON s.seller_id = sars.seller_id
LEFT JOIN
    SellerAvgPackingTimes AS sapt
    ON s.seller_id = sapt.seller_id
LEFT JOIN
    RankedSellerCategorySales AS rscs
    ON s.seller_id = rscs.seller_id AND rscs.rn = 1
ORDER BY
    ssm.total_sales DESC