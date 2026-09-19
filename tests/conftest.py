import sqlite3, sys, os, tempfile, pytest

# The suite pins the hashed embedder, whatever this machine happens to have
# installed. Catalog() now picks a sentence model when one is available, which
# is right for a user and wrong for these tests: the expected rankings are the
# hashed embedder's, the JS twin has no sentence model so parity could never
# hold, and CI installs only [dev] -- so without this, a developer with
# schemagate[huggingface] runs a different suite from the one that gates the
# merge. That exact gap (hypothesis absent locally, present in CI) already hid
# a real bug for a whole session.
os.environ.setdefault("SCHEMAGATE_AUTO_EMBEDDER", "0")
# Same reason as the line above: the suite is offline and deterministic. The
# CLI, MCP and Studio now describe the catalogue automatically when a key is
# present, and a key in the developer's shell must not turn a test run into
# forty-two billed API calls. setdefault, so a test can still opt in.
os.environ.setdefault("SCHEMAGATE_AUTO_DESCRIBE", "0")
sys.path.insert(0, os.path.dirname(__file__))
from schema_fixture import DDL, HINTS
from schemagate import Catalog

@pytest.fixture(scope="session")
def db_url():
    p = os.path.join(tempfile.mkdtemp(), "fixture.db")
    c = sqlite3.connect(p); c.executescript(DDL); c.commit(); c.close()
    return f"sqlite:///{p}"

@pytest.fixture
def cat(db_url):
    c = Catalog().bootstrap(db_url)
    for t, h in HINTS.items():
        c.hint(t, h)
    return c.index()


@pytest.fixture(scope="session", autouse=True)
def _hermetic_schemagate_home(tmp_path_factory):
    """Tests never read or write the developer's own ~/.schemagate.

    The Studio replays the remembered connection and model at start-up, on a
    thread. With a real store on the machine every test that starts a Studio
    reconnected to that database and loaded that model -- a local
    transformers pipeline, once per test, concurrently -- which is how a
    green suite turned into an access violation on one laptop and never in
    CI. A test that wants a particular store still sets SCHEMAGATE_HOME
    itself; this only supplies the empty one when nothing did.
    """
    if os.environ.get("SCHEMAGATE_HOME"):
        yield
        return
    os.environ["SCHEMAGATE_HOME"] = str(tmp_path_factory.mktemp("schemagate-home"))
    try:
        yield
    finally:
        os.environ.pop("SCHEMAGATE_HOME", None)
