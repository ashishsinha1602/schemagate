WITH MonthlyPayments AS (
    SELECT
        p.customer_id,
        c.first_name,
        c.last_name,
        STRFTIME('%Y-%m', p.payment_date) AS payment_month,
        SUM(p.amount) AS monthly_total
    FROM
        main.payment AS p
    JOIN
        main.customer AS c
        ON p.customer_id = c.customer_id
    GROUP BY
        p.customer_id,
        c.first_name,
        c.last_name,
        payment_month
), MonthlyChanges AS (
    SELECT
        customer_id,
        first_name,
        last_name,
        monthly_total - LAG(monthly_total, 1, NULL) OVER (PARTITION BY customer_id ORDER BY payment_month) AS monthly_change
    FROM
        MonthlyPayments
)
SELECT
    first_name || ' ' || last_name AS customer_full_name
FROM
    MonthlyChanges
WHERE
    monthly_change IS NOT NULL
GROUP BY
    customer_id,
    first_name,
    last_name
ORDER BY
    AVG(monthly_change) DESC
LIMIT 1