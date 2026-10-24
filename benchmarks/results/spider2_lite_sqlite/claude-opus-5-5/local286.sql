WITH seller_stats AS (
    SELECT
        oi.seller_id,
        COUNT(*) AS total_quantity_sold,
        SUM(oi.price) AS total_sales,
        AVG(oi.price) AS avg_item_price,
        AVG(julianday(o.order_delivered_carrier_date) - julianday(o.order_approved_at)) AS avg_packing_time_days
    FROM order_items oi
    JOIN orders o ON o.order_id = oi.order_id
    GROUP BY oi.seller_id
    HAVING COUNT(*) > 100
),
seller_reviews AS (
    SELECT
        so.seller_id,
        AVG(r.review_score) AS avg_review_score
    FROM (SELECT DISTINCT seller_id, order_id FROM order_items) so
    JOIN order_reviews r ON r.order_id = so.order_id
    GROUP BY so.seller_id
),
seller_categories AS (
    SELECT
        oi.seller_id,
        COALESCE(t.product_category_name_english, p.product_category_name) AS category_name_english,
        COUNT(*) AS category_volume,
        ROW_NUMBER() OVER (PARTITION BY oi.seller_id ORDER BY COUNT(*) DESC) AS rn
    FROM order_items oi
    JOIN products p ON p.product_id = oi.product_id
    LEFT JOIN product_category_name_translation t ON t.product_category_name = p.product_category_name
    GROUP BY oi.seller_id, COALESCE(t.product_category_name_english, p.product_category_name)
)
SELECT
    s.seller_id,
    s.total_quantity_sold,
    s.total_sales,
    s.avg_item_price,
    rv.avg_review_score,
    s.avg_packing_time_days,
    c.category_name_english AS top_category_english,
    c.category_volume AS top_category_volume
FROM seller_stats s
LEFT JOIN seller_reviews rv ON rv.seller_id = s.seller_id
LEFT JOIN seller_categories c ON c.seller_id = s.seller_id AND c.rn = 1
ORDER BY s.total_sales DESC