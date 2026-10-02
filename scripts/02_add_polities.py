import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import CULTURA_DB, POLITIES, SESHAT_DB

FLAGS = {
    "g": "General Variables",
    "sc": "Social Complexity Variables",
    "wf": "Warfare Variables",
    "rt": "Religion Variables",
    "hs": "Human Sacrifice",
    "cc": "Crisis Consequences",
    "pt": "Power Transition",
    "in": "Instability Events",
}

# Cultura's territories with their Seshat ids: Cultura already carries Cliopatria's SeshatID on each territory.
TERRITORIES = """
SELECT cliopatria_id, name, t.start_year AS from_year, t.end_year AS to_year, trim(unnest(string_split(t.seshat_id, ';'))) AS seshat_id
FROM (SELECT cliopatria_id, name, unnest(territories) AS t FROM polity)
WHERE t.seshat_id IS NOT NULL
"""

LINKS = """
WITH links AS (
    SELECT seshat_id, cliopatria_id, name,
        list(struct_pack(start_year := from_year, end_year := to_year) ORDER BY from_year) AS periods
    FROM periods
    GROUP BY ALL
), polity_links AS (
    SELECT seshat_id AS polity_new_id,
        list(struct_pack(cliopatria_id := cliopatria_id, name := name, periods := periods) ORDER BY cliopatria_id) AS link_to_cliopatria
    FROM links
    GROUP BY seshat_id
)
SELECT p.*, coalesce(l.link_to_cliopatria, []) AS link_to_cliopatria
FROM polities p
LEFT JOIN polity_links l USING (polity_new_id)
ORDER BY p.id
"""


def merge_periods(territories):
    """Merge the consecutive territories of a (Seshat id, Cliopatria polity) pair into periods."""
    t = territories.sort_values(["seshat_id", "cliopatria_id", "from_year"])
    same_pair = (t.seshat_id == t.seshat_id.shift()) & (t.cliopatria_id == t.cliopatria_id.shift())
    starts_new = ~same_pair | (t.from_year > t.to_year.shift().add(1))
    t["period"] = starts_new.cumsum()
    return t.groupby(["seshat_id", "cliopatria_id", "name", "period"], as_index=False).agg(
        from_year=("from_year", "min"), to_year=("to_year", "max"))


def main():
    polities = pd.read_csv(POLITIES, sep="|")
    polities.columns = [c.lower() for c in polities.columns]
    polities = polities.rename(columns={code: f"{code} ({meaning})" for code, meaning in FLAGS.items()})
    polities = polities[["polity_long_name"] + [c for c in polities.columns if c != "polity_long_name"]]
    assert polities.id.is_unique and polities.polity_new_id.is_unique and polities.polity_old_id.is_unique
    with duckdb.connect(str(CULTURA_DB), read_only=True) as cultura:
        territories = cultura.sql(TERRITORIES).df()
    periods = merge_periods(territories[territories.seshat_id != ""])
    with duckdb.connect(str(SESHAT_DB)) as con:
        con.execute(f"CREATE OR REPLACE TABLE polity AS {LINKS}")
        linked = con.sql("SELECT count(*) FILTER (WHERE len(link_to_cliopatria) > 0) FROM polity").fetchone()[0]
    print(f"{len(polities)} polities written to {SESHAT_DB.name}, {linked} linked to Cliopatria")


if __name__ == "__main__":
    main()
