WITH customer_first_purchase AS (
    SELECT
        customer_id,
        MIN(payment_date) AS first_purchase_date
    FROM
        main.payment
    GROUP BY
        customer_id
),
customer_sales_metrics AS (
    SELECT
        p.customer_id,
        SUM(p.amount) AS total_ltv,
        SUM(CASE WHEN p.payment_date <= datetime(cfp.first_purchase_date, '+7 days') THEN p.amount ELSE 0 END) AS sales_7_days,
        SUM(CASE WHEN p.payment_date <= datetime(cfp.first_purchase_date, '+30 days') THEN p.amount ELSE 0 END) AS sales_30_days
    FROM
        main.payment AS p
    JOIN
        customer_first_purchase AS cfp ON p.customer_id = cfp.customer_id
    GROUP BY
        p.customer_id
)
SELECT
    AVG(cs.sales_7_days * 100.0 / cs.total_ltv) AS avg_percentage_7_days,
    AVG(cs.sales_30_days * 100.0 / cs.total_ltv) AS avg_percentage_30_days,
    AVG(cs.total_ltv) AS avg_total_lifetime_sales
FROM
    customer_sales_metrics AS cs
WHERE
    cs.total_ltv > 0