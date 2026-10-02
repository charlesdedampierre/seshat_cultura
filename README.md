# Seshat Cultura project

Links Cultura's cultural producers to Seshat polities and compares cultural production with social complexity (Scale_1).

## Pipeline

1. `scripts/01_add_variables.py` – Seshat codebook variables into `data/processed/seshat.duckdb`
2. `scripts/02_add_polities.py` – Seshat polity list, with links to Cliopatria read from Cultura
3. `scripts/03_add_seshat_information.py` – Equinox values per polity
4. `scripts/04_add_individuals.py` – Cultura individuals with their Seshat polities (from `humans_clean_enriched_v3`)

## Notebooks

- `01_unseen_species_by_seshat_region` – generalized Chao model, writes `data/processed/unseen_species.csv`
- `02_creative_individuals_by_seshat_polity` – Scale_1 and cultural production by polity and region
- `03_association_complexity_cultural_production` – fixed-effects regressions

## Not in the repository

- `data/` – raw Seshat files (Equinox, codebook, polity list, occupation mapping) and the DuckDB
- `.env` – `CULTURA_DB`, the path to Cultura's `humans_clean_enriched_v3.duckdb` (see `.env.example`)
- `external/SeshatDatasetAnalysis` – clone of https://github.com/matildaperuzzo/SeshatDatasetAnalysis (commit 292b042), whose `datasets/polities.xlsx` gives Scale_1
