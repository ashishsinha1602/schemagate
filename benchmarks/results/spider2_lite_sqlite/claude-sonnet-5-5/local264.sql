SELECT L1_model, COUNT(*) AS total_count
FROM model
GROUP BY L1_model
ORDER BY total_count DESC
LIMIT 1