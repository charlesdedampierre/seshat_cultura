import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

RAW = ROOT / "data/raw"
SESHAT_DB = Path(os.environ.get("SESHAT_DB", ROOT / "data/processed/seshat.duckdb"))
CODEBOOK = RAW / "Legacy Codebook (Equinox).txt"
EQUINOX = RAW / "Equinox2020.05.2023.xlsx"
POLITIES = RAW / "polities_20260929_110619.csv"
OCCUPATION_MAPPING = RAW / "occupation_mapping.csv"  # from cultura/2-cultura_database_extract/2 - extract_CPs_works.ipynb

CULTURA_DB = Path(os.environ["CULTURA_DB"])
