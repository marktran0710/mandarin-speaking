-- pytest runs against its own database so tests can TRUNCATE freely without
-- touching development data. See backend/tests/conftest.py.
CREATE DATABASE mandarin_test OWNER mandarin;
