-- patch.sql

-- Check if column already exists (Postgres 9.6+ trick)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name='trades' 
          AND column_name='account_login'
    ) THEN
        ALTER TABLE trades ADD COLUMN account_login VARCHAR(50);
    END IF;
END
$$;
