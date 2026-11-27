"""Local stand-in for BIRD-CRITIC's postgres Docker image: a private cluster on C:, port 5544, user root (trust),
template DBs loaded exactly as env/init-databases_postgresql.sh does, then real DBs cloned from the templates."""
import os
import subprocess
import time
from pathlib import Path

BIN = Path(r"C:\Program Files\PostgreSQL\17\bin")
DATA = Path(r"C:\birdcritic\pgdata")
DUMPS = Path(r"C:\birdcritic\unz\postgre_table_dumps")
PORT = "5544"
PSQL = r"C:\Program Files\PostgreSQL\17\pgAdmin 4\runtime\psql.exe"
ENV = dict(os.environ, PGPORT=PORT, PGHOST="127.0.0.1", PGUSER="root")

MAPPING = {
    "debit_card_specializing_template": "customers gasstations products yearmonth transactions_1k",
    "financial_template": "district client account disp loan trans card order",
    "formula_1_template": "circuits status drivers driverstandings seasons constructors races constructorresults laptimes qualifying pitstops constructorstandings results",
    "california_schools_template": "schools satscores frpm",
    "card_games_template": "legalities cards rulings sets set_translations foreign_data",
    "european_football_2_template": "team league country player team_attributes player_attributes match",
    "thrombosis_prediction_template": "patient laboratory examination",
    "toxicology_template": "molecule bond atom connected",
    "student_club_template": "zip_code event major budget member income expense attendance",
    "superhero_template": "gender alignment colour attribute publisher superpower race superhero hero_power hero_attribute",
    "codebase_community_template": "tags postlinks users posthistory badges comments posts votes",
    "erolp_template": "learners institutions curricula educational_resources external_factors outcomes enrollment curriculum_resources resource_usage performance_predictions target_labels",
    "esophageal_template": "patients demographics lifestyle_and_risk_factors patient_addresses clinical_status icd_classifications patient_icd_codes staging_systems patient_staging pathology_and_surgery treatment_and_followup",
    "global_atlas_template": "country city province economy population politics religion ethnicgroup spoken language countrypops countryothername countrylocalname provpops provinceothername provincelocalname citypops cityothername citylocalname continent borders encompasses organization ismember",
    "spotify_template": "sp_artists sp_albums sp_album_ctb sp_tracks sp_album_tracks sp_track_artists sp_track_info sp_audio_feats",
}


def psql(*args, db="postgres", check=False):
    return subprocess.run([PSQL, "-v", "ON_ERROR_STOP=0", "-q", "-d", db, *args],
                          env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace", check=check)


def main():
    if not DATA.exists():
        subprocess.run([str(BIN / "initdb.exe"), "-D", str(DATA), "-U", "root", "--auth=trust", "-E", "UTF8",
                        "--locale=C"], check=True)
        with open(DATA / "postgresql.conf", "a") as f:
            f.write(f"\nport = {PORT}\nlisten_addresses = '127.0.0.1'\nmax_connections = 300\nshared_buffers = 512MB\n"
                    "max_prepared_transactions = 50\ntimezone = 'Asia/Hong_Kong'\n")
    r = subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(DATA), "status"], capture_output=True, text=True)
    if "server is running" not in r.stdout:
        subprocess.Popen([str(BIN / "pg_ctl.exe"), "-D", str(DATA), "-l", str(DATA.parent / "pg.log"), "start"])
        for _ in range(60):
            if psql("-c", "select 1").returncode == 0:
                break
            time.sleep(1)
    print("server up")
    psql("-c", "CREATE DATABASE sql_test_template WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;")
    for s in ("CREATE SCHEMA IF NOT EXISTS test_schema;", "CREATE SCHEMA IF NOT EXISTS test_schema_2;",
              "CREATE EXTENSION IF NOT EXISTS hstore;", "CREATE EXTENSION IF NOT EXISTS citext;",
              "ALTER DATABASE sql_test_template SET default_text_search_config = 'pg_catalog.english';"):
        psql("-c", s, db="sql_test_template")
    errs = open(DATA.parent / "import_errors.log", "w", encoding="utf-8")
    for tpl, tables in MAPPING.items():
        exists = psql("-tAc", f"SELECT 1 FROM pg_database WHERE datname='{tpl}'").stdout.strip()
        if exists:
            print("exists", tpl)
            continue
        psql("-c", f"CREATE DATABASE {tpl} WITH OWNER=root ENCODING='UTF8' TEMPLATE=template0;")
        folder = DUMPS / tpl
        files = ([folder / "global_atlas-schema.sql", folder / "global_atlas-inputs.sql"]
                 if tpl == "global_atlas_template" and (folder / "global_atlas-schema.sql").exists()
                 else [folder / f"{t}.sql" for t in tables.split()])
        for f in files:
            if not f.exists():
                print("  missing", f.name)
                continue
            r = psql("-f", str(f), db=tpl)
            if r.stderr.strip():
                errs.write(f"== {tpl}/{f.name}\n{r.stderr[:3000]}\n")
        print("loaded", tpl, flush=True)
    for tpl in MAPPING:
        psql("-c", f"UPDATE pg_database SET datistemplate = true WHERE datname = '{tpl}';")
        real = tpl[: -len("_template")]
        if not psql("-tAc", f"SELECT 1 FROM pg_database WHERE datname='{real}'").stdout.strip():
            psql("-c", f"CREATE DATABASE {real} WITH OWNER=root TEMPLATE={tpl};")
    print(psql("-tAc", "select datname from pg_database order by 1").stdout)


if __name__ == "__main__":
    main()
