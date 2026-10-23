WITH DeliveredOrderItems AS (
    SELECT
        o.order_id,
        o.customer_id,
        oi.seller_id,
        oi.price,
        oi.freight_value
    FROM
        main.olist_orders AS o
    JOIN
        main.olist_order_items AS oi ON o.order_id = oi.order_id
    WHERE
        o.order_status = 'delivered'
),
-- Metric 1: Highest number of distinct customer unique IDs
DistinctCustomersPerSeller AS (
    SELECT
        doi.seller_id,
        COUNT(DISTINCT c.customer_unique_id) AS distinct_customers_count
    FROM
        DeliveredOrderItems AS doi
    JOIN
        main.olist_customers AS c ON doi.customer_id = c.customer_id
    GROUP BY
        doi.seller_id
),
TopDistinctCustomers AS (
    SELECT
        'Highest Distinct Customers' AS achievement,
        seller_id,
        distinct_customers_count AS value
    FROM
        DistinctCustomersPerSeller
    ORDER BY
        distinct_customers_count DESC
    LIMIT 1
),
-- Metric 2: Highest profit (price - freight value)
ProfitPerSeller AS (
    SELECT
        seller_id,
        SUM(price - freight_value) AS total_profit
    FROM
        DeliveredOrderItems
    GROUP BY
        seller_id
),
TopProfit AS (
    SELECT
        'Highest Profit' AS achievement,
        seller_id,
        total_profit AS value
    FROM
        ProfitPerSeller
    ORDER BY
        total_profit DESC
    LIMIT 1
),
-- Metric 3: Highest number of distinct orders
DistinctOrdersPerSeller AS (
    SELECT
        seller_id,
        COUNT(DISTINCT order_id) AS distinct_orders_count
    FROM
        DeliveredOrderItems
    GROUP BY
        seller_id
),
TopDistinctOrders AS (
    SELECT
        'Highest Distinct Orders' AS achievement,
        seller_id,
        distinct_orders_count AS value
    FROM
        DistinctOrdersPerSeller
    ORDER BY
        distinct_orders_count DESC
    LIMIT 1
),
-- Metric 4: Most 5-star ratings
FiveStarReviewsPerSeller AS (
    SELECT
        doi.seller_id,
        COUNT(r.review_id) AS five_star_reviews_count
    FROM
        DeliveredOrderItems AS doi
    JOIN
        main.olist_order_reviews AS r ON doi.order_id = r.order_id
    WHERE
        r.review_score = 5
    GROUP BY
        doi.seller_id
),
TopFiveStarReviews AS (
    SELECT
        'Most 5-Star Ratings' AS achievement,
        seller_id,
        five_star_reviews_count AS value
    FROM
        FiveStarReviewsPerSeller
    ORDER BY
        five_star_reviews_count DESC
    LIMIT 1
)
SELECT achievement, seller_id, value FROM TopDistinctCustomers
UNION ALL
SELECT achievement, seller_id, value FROM TopProfit
UNION ALL
SELECT achievement, seller_id, value FROM TopDistinctOrders
UNION ALL
SELECT achievement, seller_id, value FROM TopFiveStarReviews