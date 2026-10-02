import sys
import tempfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "datamodels"))

from datamodel_seshat import Individual
from config import CULTURA_DB, SESHAT_DB

# Columns copied from Cultura's individual: column -> the field_provenance entry they take
COPIED = {
    "wikidata_id": "i.field_provenance['entity']",
    "label_en": "i.field_provenance['entity']",
    "birth_date": "i.field_provenance['birth_date']",
    "death_date": "i.field_provenance['death_date']",
    "occupation": "i.field_provenance['occupation']",
    "is_artist": "i.field_provenance['is_artist']",
    "is_scientist": "i.field_provenance['is_scientist']",
}
# Columns this project builds: column -> (raw, inputs, rule)
BUILT = {
    "number_of_works": (
        ["IndividualWikidata.work"],
        ["Individual.work"],
        "The number of distinct work_qid in Cultura's Individual.work.",
    ),
    "cliopatria_polity": (
        [],
        ["IndividualEnriched.polity"],
        "The main polity of Cultura's assignments — a sub-polity before a meta polity, then the most years_spent_in_polity, "
        "then Cultura's order — as Cultura's polity table has it: its id, name and Wikidata entity, without its territories.",
    ),
    "seshat_polity": (
        [],
        ["IndividualEnriched.polity.seshat_ids"],
        "The rows of Seshat's polity list whose polity_new_id is one of the seshat_ids Cultura gives the main polity's "
        "assignment, split on ';', ordered by id.",
    ),
}
NO_AI = "NULL::STRUCT(model_name VARCHAR, prompt_id VARCHAR)"


def quote(text):
    return "'" + text.replace("'", "''") + "'"


def provenance_sql():
    built = {
        col: f"struct_pack(raw := {raw}::VARCHAR[], inputs := {inputs}::VARCHAR[], rule := {quote(rule)}, "
             f"ai_answer := {NO_AI}, retrieved_on := NULL::DATE)"
        for col, (raw, inputs, rule) in BUILT.items()
    }
    entries = ", ".join(f"struct_pack(key := {quote(k)}, value := {v})" for k, v in {**COPIED, **built}.items())
    return f"map_from_entries(list_filter([{entries}], e -> e.value IS NOT NULL))"


POLITIES = """
CREATE OR REPLACE TEMP TABLE linked_polity AS
SELECT p.cliopatria_id, struct_pack(
    cliopatria_id := p.cliopatria_id, name := p.name,
    entity := struct_pack(qid := p.entity.qid, label_en := p.entity.label_en, description := p.entity.description),
    field_provenance := map_from_entries(list_filter(map_entries(p.field_provenance),
                                                     e -> e.key IN ('cliopatria_id', 'name', 'entity')))
) AS cliopatria_polity
FROM cultura.polity p
WHERE p.cliopatria_id IN (SELECT cliopatria_id FROM main_polity)
"""

# The main polity of each individual — a sub-polity before a meta polity, then the most years, then Cultura's order —
# with the Seshat ids Cultura gives that assignment, split on ';' and kept when Seshat's list has them.
MAIN = """
CREATE OR REPLACE TEMP TABLE main_polity AS
WITH main AS (
    SELECT * FROM (
        SELECT entity.qid AS qid, generate_subscripts(polity, 1) AS pos, unnest([struct_pack(
            cliopatria_id := p.polity.cliopatria_id, is_meta := len(p.polity.child_polities) > 0,
            years := p.years_spent_in_polity, seshat_ids := p.seshat_ids) FOR p IN polity]) AS a
        FROM cultura.individual_enriched
        WHERE polity_count > 0
    )
    QUALIFY row_number() OVER (PARTITION BY qid ORDER BY a.is_meta, a.years DESC, pos) = 1
), ids AS (
    SELECT qid, a.cliopatria_id AS cliopatria_id,
        trim(unnest(flatten([string_split(s, ';') FOR s IN a.seshat_ids]))) AS id
    FROM main
)
SELECT qid, cliopatria_id, list_sort(list(DISTINCT id)) AS seshat_ids
FROM ids
WHERE id IN (SELECT polity_new_id FROM polity)
GROUP BY ALL
"""

# Cultura's individuals carry only the qid of their occupations: the labels are on its occupation table.
OCCUPATIONS = """
CREATE OR REPLACE TEMP TABLE individual_occupation AS
SELECT x.qid, list(coalesce(o.entity, x.occupation) ORDER BY x.pos) AS occupation
FROM (
    SELECT entity.qid AS qid, unnest([o.entity FOR o IN occupation]) AS occupation, generate_subscripts(occupation, 1) AS pos
    FROM cultura.individual
    WHERE entity.qid IN (SELECT qid FROM main_polity)
) x
LEFT JOIN cultura.occupation o ON o.entity.qid = x.occupation.qid
GROUP BY x.qid
"""

# The Seshat polity rows built once per distinct set of ids, not once per individual.
SESHAT_SET = """
CREATE OR REPLACE TEMP TABLE seshat_set AS
SELECT s.seshat_ids, list(sp ORDER BY sp.id) AS seshat_polity
FROM (SELECT DISTINCT seshat_ids FROM main_polity) s
CROSS JOIN unnest(s.seshat_ids) AS u(polity_new_id)
JOIN polity sp USING (polity_new_id)
GROUP BY s.seshat_ids
"""

BUILD = """
CREATE OR REPLACE TABLE individual AS
SELECT
    i.entity.qid AS wikidata_id,
    i.entity.label_en AS label_en,
    i.birth_date,
    i.death_date,
    coalesce(io.occupation, []) AS occupation,
    len(list_distinct([w.work_qid FOR w IN i.work])) AS number_of_works,
    i.is_artist,
    i.is_scientist,
    lp.cliopatria_polity,
    s.seshat_polity,
    {provenance} AS field_provenance
FROM cultura.individual i
JOIN main_polity x ON x.qid = i.entity.qid
JOIN seshat_set s USING (seshat_ids)
JOIN linked_polity lp USING (cliopatria_id)
LEFT JOIN individual_occupation io ON io.qid = x.qid
"""


def main():
    with duckdb.connect(str(SESHAT_DB)) as con:
        con.execute(f"SET memory_limit='8GB'; SET temp_directory='{tempfile.mkdtemp()}'; SET enable_progress_bar=true; SET preserve_insertion_order=false; SET threads=4")
        con.execute(f"ATTACH '{CULTURA_DB}' AS cultura (READ_ONLY)")
        for step in (MAIN, POLITIES, OCCUPATIONS, SESHAT_SET):
            con.execute(step)
        con.execute(BUILD.format(provenance=provenance_sql()))
        columns = [r[0] for r in con.execute("DESCRIBE individual").fetchall()]
        assert columns == list(Individual.model_fields), columns
        sample = con.execute("SELECT * FROM individual USING SAMPLE 1000 ROWS")
        for row in sample.fetchall():
            Individual.model_validate(dict(zip(columns, row)))
        seshat = con.sql("SELECT count(DISTINCT s.id) FROM (SELECT unnest(seshat_polity) AS s FROM individual)").fetchone()[0]
        n = con.sql("SELECT count(*), sum(is_artist::INT), sum(is_scientist::INT) FROM individual").fetchone()
    print(f"{n[0]} individuals linked to {seshat} Seshat polities written to {SESHAT_DB.name} "
          f"({n[1]} artists, {n[2]} scientists)")


if __name__ == "__main__":
    main()
