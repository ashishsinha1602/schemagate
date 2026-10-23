WITH OrderCategoryMapping AS (
    SELECT DISTINCT
        oi.order_id,
        pct.product_category_name_english
    FROM
        main.olist_order_items AS oi
    JOIN
        main.olist_products AS p
        ON oi.product_id = p.product_id
    JOIN
        main.product_category_name_translation AS pct
        ON p.product_category_name = pct.product_category_name
),
CategoryPaymentCounts AS (
    SELECT
        ocm.product_category_name_english,
        op.payment_type,
        COUNT(op.order_id) AS payment_count
    FROM
        OrderCategoryMapping AS ocm
    JOIN
        main.olist_order_payments AS op
        ON ocm.order_id = op.order_id
    GROUP BY
        ocm.product_category_name_english,
        op.payment_type
),
RankedCategoryPayments AS (
    SELECT
        product_category_name_english,
        payment_type,
        payment_count,
        ROW_NUMBER() OVER (PARTITION BY product_category_name_english ORDER BY payment_count DESC, payment_type ASC) AS rn
    FROM
        CategoryPaymentCounts
)
SELECT
    product_category_name_english,
    payment_count
FROM
    RankedCategoryPayments
WHERE
    rn = 1
ORDER BY
    payment_count DESC
LIMIT 3