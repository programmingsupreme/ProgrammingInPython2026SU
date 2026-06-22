-- Database: VNBookstore

-- DROP DATABASE IF EXISTS "VNBookstore";

CREATE DATABASE "VNBookstore"
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'C'
    LC_CTYPE = 'C'
    LOCALE_PROVIDER = 'libc'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1
    IS_TEMPLATE = False;

COMMENT ON DATABASE "VNBookstore"
    IS 'CPS3320';