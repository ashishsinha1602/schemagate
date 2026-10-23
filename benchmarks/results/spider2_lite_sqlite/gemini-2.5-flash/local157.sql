WITH cleaned_data AS (
    SELECT
        ticker,
        market_date,
        CASE
            WHEN volume = '-' THEN 0.0
            WHEN volume LIKE '%K' THEN CAST(REPLACE(volume, 'K', '') AS REAL) * 1000
            WHEN volume LIKE '%M' THEN CAST(REPLACE(volume, 'M', '') AS REAL) * 1000000
            ELSE CAST(volume AS REAL)
        END AS current_volume
    FROM
        main.bitcoin_prices
    WHERE
        market_date BETWEEN '2021-08-01' AND '2021-08-10'
),
data_with_prev_non_zero_volume AS (
    SELECT
        cd1.ticker,
        cd1.market_date,
        cd1.current_volume,
        (
            SELECT cd2.current_volume
            FROM cleaned_data cd2
            WHERE
                cd2.ticker = cd1.ticker
                AND cd2.market_date < cd1.market_date
                AND cd2.current_volume > 0
            ORDER BY cd2.market_date DESC
            LIMIT 1
        ) AS prev_non_zero_volume
    FROM
        cleaned_data cd1
)
SELECT
    ticker,
    market_date,
    CASE
        WHEN prev_non_zero_volume IS NULL THEN NULL
        ELSE ((current_volume - prev_non_zero_volume) * 100.0 / prev_non_zero_volume)
    END AS daily_percentage_change
FROM
    data_with_prev_non_zero_volume
ORDER BY
    ticker,
    market_date