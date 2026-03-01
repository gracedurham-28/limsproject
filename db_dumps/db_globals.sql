--
-- PostgreSQL database cluster dump
--

\restrict Fw29aSS2hMlHfclTaAlYMGrhwr5Gd3ddEgg8RIKBI6iOrKmnoGODyUG0uyKx5KY

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE postgres;
ALTER ROLE postgres WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'SCRAM-SHA-256$4096:6yzD3P0hX/xfDSCGNq4gPQ==$eVNvZa/+6h9UCAuis52FpjykRDSvN3Aw8CMQ/jkmsC8=:yoyGSDAFgkgKa2SM22y+xDEupfOpYiOhhMKc9vs2j7I=';

--
-- User Configurations
--








\unrestrict Fw29aSS2hMlHfclTaAlYMGrhwr5Gd3ddEgg8RIKBI6iOrKmnoGODyUG0uyKx5KY

--
-- PostgreSQL database cluster dump complete
--

