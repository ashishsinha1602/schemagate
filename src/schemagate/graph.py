# Copyright 2026 Ashish Sinha. Licensed under the Apache License, Version 2.0.
"""The schema as a property graph, built from what the database already says.

Nodes carry a label and properties: ``Table``, ``View``, ``Endpoint``, ``Column``,
``Concept``. Edges do too:

    HAS_COLUMN    Table -> Column
    REFERENCES    Table -> Table      a foreign key, declared or ``inferred``
    DERIVED_FROM  View  -> Table      the view's SQL reads it
    JOINS         Table -> Table      a view's SQL, or the query log, joins them on these columns
    QUERIED_WITH  Table -> Table      the query log reads them in one statement
    MAPS_TO       Concept -> Table or Column
    BROADER       Concept -> Concept

``Catalog.graph(principal)`` builds one for a caller. It follows the same rules as
the prompt: an object or column the caller may not see is not a node, an edge
needs both of its ends, and a concept that would name something withheld is left
out whole. So a graph can be handed to the caller it was built for.

``Catalog.pull_concepts()`` proposes concepts from the database itself, with no
file to export and no model call:

* a short table or column comment is a business term for it (``ttl_amt``,
  "Total amount");
* a longer column comment is that column's definition;
* a view's ``WHERE`` defines the view's name ("paid invoices"), and a computed
  column defines its alias (``SUM(total_net) AS revenue``).

What it proposes can only be as good as those comments and views. A term the
database never wrote down still needs a person. Reading view SQL needs sqlglot
(``pip install 'schemagate[graph]'``); without it comments still work, and the
report says what was skipped.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from .embedder import tokenize
from .ontology import STOP, phrase_key

#: SQLAlchemy dialect name -> sqlglot's.
SQLGLOT_DIALECTS = {"postgresql": "postgres", "mssql": "tsql", "mysql": "mysql",
                    "mariadb": "mysql", "oracle": "oracle", "sqlite": "sqlite"}

#: A comment this short names the thing; a longer one explains it.
_TERM_WORDS = 4
#: A longer rule than this is not going into a one-line meaning.
_MAX_TEXT = 300
#: Comments about the column's upkeep, not its meaning.
_NOT_A_TERM = frozenset("deprecated legacy unused obsolete todo tbd fixme temp temporary".split())
_NOT_A_TERM_PHRASES = ("do not use", "dont use", "not used", "no longer used")
#: Aliases too general to mean one thing across a database.
_GENERIC = frozenset("""
amount cnt count id idx key max min name num qty result status sum total type val value
""".split())
_VIEW_AFFIX = re.compile(r"^(?:vw?|view)_|_(?:vw?|view)$", re.I)
_XML_BAD = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")   # raw: the regex engine reads the escapes


@dataclass
class Node:
    id: str
    label: str
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    label: str
    props: Dict[str, Any] = field(default_factory=dict)


class PropertyGraph:
    """Nodes and edges. An edge whose end is not a node is dropped, not kept dangling."""

    def __init__(self) -> None:
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        #: What could not be read, for a person.
        self.notes: List[str] = []

    def add_node(self, id: str, label: str, **props: Any) -> None:
        self.nodes[id] = Node(id, label, {k: v for k, v in props.items() if v not in (None, [], "")})

    def add_edge(self, source: str, target: str, label: str, **props: Any) -> bool:
        """Add an edge if both ends exist and it is new. Returns whether it was added."""
        if source not in self.nodes or target not in self.nodes:
            return False
        edge = Edge(source, target, label, {k: v for k, v in props.items() if v not in (None, [], "")})
        if edge in self.edges:
            return False
        self.edges.append(edge)
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {"nodes": [{"id": n.id, "label": n.label, "properties": n.props} for n in self.nodes.values()],
                "edges": [{"source": e.source, "target": e.target, "label": e.label, "properties": e.props}
                          for e in self.edges],
                "notes": list(self.notes)}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_graphml(self) -> str:
        """GraphML, for yEd, Gephi, networkx and most graph databases' importers."""
        root = ET.Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
        keys = {("node", "label"), ("edge", "label")}
        keys |= {("node", k) for n in self.nodes.values() for k in n.props}
        keys |= {("edge", k) for e in self.edges for k in e.props}
        for scope, name in sorted(keys):
            ET.SubElement(root, "key", {"id": f"{scope}_{name}", "for": scope, "attr.name": name,
                                        "attr.type": "string"})
        graph = ET.SubElement(root, "graph", edgedefault="directed")

        def fill(parent, scope, label, props):
            for name, value in [("label", label), *props.items()]:
                text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                ET.SubElement(parent, "data", key=f"{scope}_{name}").text = _XML_BAD.sub(" ", text)

        for n in self.nodes.values():
            fill(ET.SubElement(graph, "node", id=n.id), "node", n.label, n.props)
        for e in self.edges:
            fill(ET.SubElement(graph, "edge", source=e.source, target=e.target), "edge", e.label, e.props)
        return ET.tostring(root, encoding="unicode")

    def summary(self) -> str:
        def count(items) -> str:
            found: Dict[str, int] = {}
            for i in items:
                found[i.label] = found.get(i.label, 0) + 1
            return ", ".join(f"{v} {k}" for k, v in sorted(found.items())) or "none"
        return f"nodes: {count(self.nodes.values())}\nedges: {count(self.edges)}"


# ------------------------------------------------------------------ view SQL

@dataclass
class ViewFacts:
    """What a view's SQL says, with table aliases replaced by the real names."""
    tables: List[str] = field(default_factory=list)
    where: Optional[str] = None
    computed: List[Tuple[str, str]] = field(default_factory=list)                # (alias, expression)
    joins: List[Tuple[str, str, str, str]] = field(default_factory=list)         # (table, column, table, column)


def read_view(definition: str, dialect: Optional[str] = None) -> Optional[ViewFacts]:
    """Read a view's SQL. None without sqlglot or if it cannot be parsed."""
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:
        return None
    read = SQLGLOT_DIALECTS.get(dialect or "", dialect)
    try:
        tree = sqlglot.parse_one(definition, read=read)
    except Exception:                                    # noqa: BLE001 -- any parse failure
        return None
    query = tree.expression if isinstance(tree, exp.Create) else tree
    if query is None:
        return None
    ctes = {(c.alias_or_name or "").lower() for c in query.find_all(exp.CTE)}
    aliases: Dict[str, str] = {}
    facts = ViewFacts()
    for t in query.find_all(exp.Table):
        if t.name and t.name.lower() not in ctes:
            aliases[(t.alias_or_name or t.name).lower()] = t.name
            if t.name not in facts.tables:
                facts.tables.append(t.name)
    if not isinstance(query, exp.Select):                # a UNION has no single filter or column list
        return facts

    def render(node) -> str:
        # Real table names and no quotes: the visibility check reads this text,
        # and it must see `employee.salary`, not `e.salary` or `"employee"."salary"`.
        node = node.copy()
        for c in node.find_all(exp.Column):
            real = aliases.get((c.table or "").lower())
            if real:
                c.set("table", exp.to_identifier(real))
        for i in node.find_all(exp.Identifier):
            i.set("quoted", False)

        # Postgres stores `status = 'paid'` as `((status = 'paid'::text))`. Same rule, harder
        # to read. A holder, so the top node can be replaced like any other.
        holder = exp.Paren(this=node)
        text_types = {exp.DataType.Type.TEXT, exp.DataType.Type.VARCHAR}
        for cast in list(node.find_all(exp.Cast)):
            inner = cast.this.unnest()
            if isinstance(inner, exp.Literal) or (isinstance(inner, exp.Column) and cast.to.this in text_types):
                cast.replace(inner)
        for paren in list(holder.this.find_all(exp.Paren)):
            if isinstance(paren.this.unnest(), (exp.Predicate, exp.Literal, exp.Column)):
                paren.replace(paren.this.unnest())
        return " ".join(holder.unnest().sql(dialect=read).split())

    where = query.args.get("where")
    if where is not None:
        facts.where = render(where.this)
    for e in query.selects:
        if isinstance(e, exp.Alias) and not isinstance(e.this, (exp.Column, exp.Literal)):
            facts.computed.append((e.alias, render(e.this)))
    # Not query.args["joins"]: Postgres stores `FROM (a JOIN b ON ...)`, which nests them.
    for j in query.find_all(exp.Join):
        on = j.args.get("on")
        for eq in (on.find_all(exp.EQ) if on is not None else ()):
            left, right = eq.this, eq.expression
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                a, b = aliases.get((left.table or "").lower()), aliases.get((right.table or "").lower())
                if a and b:
                    facts.joins.append((a, left.name, b, right.name))
    return facts


# -------------------------------------------------------------------- graph

def _find_doc(docs, ref: str, near_schema: Optional[str]):
    """The object a reference means, or None if it is outside the catalog or ambiguous."""
    ref = (ref or "").lower()
    for d in docs:
        if d.qname.lower() == ref:
            return d
    named = [d for d in docs if d.name.lower() == ref.split(".")[-1]]
    if len(named) == 1:
        return named[0]
    nearby = [d for d in named if (d.schema or "").lower() == (near_schema or "").lower()]
    return nearby[0] if len(nearby) == 1 else None


def build_graph(cat, principal=None, dialect: Optional[str] = None) -> PropertyGraph:
    """The graph this caller may see. See ``Catalog.graph``."""
    from .learn import referenced_tables
    g = PropertyGraph()
    every = cat.objects()
    shown = {d.qname: d for d in every if cat._visible(d, principal)}
    columns = {q: {c.name.lower() for c in d.visible_columns(principal)} for q, d in shown.items()}

    def may_read(q: str, names) -> bool:
        return all((n or "").lower() in columns.get(q, ()) for n in names)

    for q, d in shown.items():
        g.add_node(f"object:{q}", {"VIEW": "View", "ENDPOINT": "Endpoint"}.get(d.kind, "Table"),
                   name=d.name, schema=d.schema, qname=q, row_estimate=d.row_estimate,
                   description=d.hint or d.description)
        for c in d.visible_columns(principal):
            g.add_node(f"column:{q}.{c.name}", "Column", name=c.name, type=c.type, pk=c.pk or None,
                       nullable=c.nullable, comment=c.comment)
            g.add_edge(f"object:{q}", f"column:{q}.{c.name}", "HAS_COLUMN")

    for q, d in shown.items():
        for fk in d.foreign_keys:
            target = _find_doc(every, fk.ref_table, d.schema)
            if target is None or target.qname not in shown:
                continue
            if may_read(q, fk.columns) and may_read(target.qname, fk.ref_columns):
                g.add_edge(f"object:{q}", f"object:{target.qname}", "REFERENCES",
                           columns=list(fk.columns), ref_columns=list(fk.ref_columns),
                           inferred=fk.inferred or None)

    unread: List[str] = []
    for q, d in shown.items():
        if d.kind != "VIEW" or not d.definition:
            continue
        facts = read_view(d.definition, dialect)
        if facts is None:
            unread.append(d.name)
            facts = ViewFacts(tables=referenced_tables(d.definition))
        for name in facts.tables:
            target = _find_doc(every, name, d.schema)
            if target is not None and target.qname in shown and target.qname != q:
                g.add_edge(f"object:{q}", f"object:{target.qname}", "DERIVED_FROM")
        for t1, c1, t2, c2 in facts.joins:
            a, b = _find_doc(every, t1, d.schema), _find_doc(every, t2, d.schema)
            if a is None or b is None or a.qname not in shown or b.qname not in shown:
                continue
            if may_read(a.qname, [c1]) and may_read(b.qname, [c2]):
                g.add_edge(f"object:{a.qname}", f"object:{b.qname}", "JOINS",
                           columns=[c1], ref_columns=[c2], via=q)
    if unread:
        g.notes.append(f"joins and filters not read from {len(unread)} view(s) (sqlglot missing or "
                       f"could not parse): {', '.join(sorted(unread)[:20])}")

    log = getattr(cat, "query_log", None)
    if log:
        for (qa, ca, qb, cb), n in sorted(log.joins.items(), key=lambda kv: (-kv[1], kv[0])):
            if qa in shown and qb in shown and may_read(qa, [ca]) and may_read(qb, [cb]):
                g.add_edge(f"object:{qa}", f"object:{qb}", "JOINS", columns=[ca], ref_columns=[cb],
                           via="query log", count=n)
        for pair, n in sorted(log.together.items(), key=lambda kv: (-kv[1], sorted(kv[0]))):
            a, b = sorted(pair)
            if a in shown and b in shown:
                g.add_edge(f"object:{a}", f"object:{b}", "QUERIED_WITH", count=n)
        for q, counter in log.filters.items():
            if q in shown:
                usual = [text for (col, text), _ in counter.most_common(10) if may_read(q, [col])][:5]
                if usual:
                    g.nodes[f"object:{q}"].props["common_filters"] = usual

    hidden = cat._hidden_names(principal)
    concepts = [c for c in cat.ontology.concepts.values() if cat._concept_allowed(c, principal, hidden)]
    for c in concepts:
        g.add_node(f"concept:{c.name}", "Concept", name=c.name, synonyms=list(c.synonyms),
                   filter=c.filter, definition=c.definition, source=c.source)
    for c in concepts:
        for q in c.objects:
            g.add_edge(f"concept:{c.name}", f"object:{q}", "MAPS_TO")
        for q, col in c.columns:
            g.add_edge(f"concept:{c.name}", f"column:{q}.{col}", "MAPS_TO")
        for b in c.broader:
            parent = cat.ontology.get(b)
            if parent is not None:
                g.add_edge(f"concept:{c.name}", f"concept:{parent.name}", "BROADER")
    return g


# ------------------------------------------------------- the database's own graph

#: Whose ``CREATE PROPERTY GRAPH`` this writes, each run on a real server: Oracle 23ai and later.
#: Not PostgreSQL: 19rc1 rejects the syntax, and its release notes do not mention it.
NATIVE_GRAPH_DIALECTS = ("oracle",)
#: Oracle allows 128 bytes for a name; a label built from two table names and a column
#: can pass that, so longer ones are cut and given a short hash to stay unique.
_MAX_ALIAS = 100


def create_graph_sql(cat, principal=None, dialect: Optional[str] = None,
                     name: str = "schemagate_graph") -> str:
    """``CREATE PROPERTY GRAPH`` for the tables this caller may see. See ``Catalog.create_graph_sql``."""
    import hashlib
    if dialect not in NATIVE_GRAPH_DIALECTS:
        raise ValueError(f"CREATE PROPERTY GRAPH is written for Oracle 23ai and later, not "
                         f"{dialect or 'this database'}; use --format json or graphml")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name or ""):
        raise ValueError(f"graph name {name!r}: use letters, digits and underscores")

    def q(identifier: str) -> str:
        # Always quoted, so a table called `order` works. Oracle stores unquoted names in
        # upper case and SQLAlchemy reports them in lower, so lower case goes back up.
        n = identifier.upper() if identifier == identifier.lower() else identifier
        return '"' + n.replace('"', '""') + '"'

    def cols(names) -> str:
        return ", ".join(q(n) for n in names)

    def element(alias: str) -> str:
        # An alias is built from several names, so one upper-case part would leave it
        # mixed case, which Oracle then matches only when quoted exactly that way.
        return q(alias.upper())

    g = build_graph(cat, principal, dialect=dialect)
    notes = list(g.notes)
    vertices: Dict[str, Tuple[Any, str, List[str]]] = {}          # qname -> (doc, alias, key)
    taken = {d.name.lower(): 0 for d in cat.objects()}
    for d in cat.objects():
        taken[d.name.lower()] += 1
    for node in g.nodes.values():
        if node.label != "Table":
            continue
        d = cat._docs[node.props["qname"]]
        key = [c.name for c in d.columns if c.pk]
        readable = {c.name for c in d.visible_columns(principal)}
        if not key:
            notes.append(f"{d.qname} left out: no primary key to identify its rows")
        elif not set(key) <= readable:
            notes.append(f"{d.qname} left out: this caller may not read its primary key")
        else:
            alias = d.name if taken[d.name.lower()] == 1 else f"{d.schema}_{d.name}"
            vertices[d.qname] = (d, alias, key)

    def table(d) -> str:
        return f"{q(d.schema)}.{q(d.name)}" if d.schema else q(d.name)

    edges: List[str] = []
    seen = set()
    guessed = 0
    for e in g.edges:
        if e.label not in ("REFERENCES", "JOINS"):
            continue
        source, target = e.source.split(":", 1)[1], e.target.split(":", 1)[1]
        columns, refs = list(e.props.get("columns") or []), list(e.props.get("ref_columns") or [])
        if source not in vertices or target not in vertices or not refs:
            continue
        key_of = lambda v: {k.lower() for k in vertices[v][2]}  # noqa: E731
        lower = lambda names: {n.lower() for n in names}        # noqa: E731
        if lower(refs) != key_of(target) and lower(columns) == key_of(source):
            # A view can write the join either way round; an edge points at the key.
            source, target, columns, refs = target, source, refs, columns
        if lower(refs) != key_of(target):
            notes.append(f"edge {source} -> {target} left out: {', '.join(refs)} is not the key of {target}")
            continue
        identity = (source, tuple(columns), target, tuple(refs))
        if identity in seen:
            continue
        seen.add(identity)
        guessed += 1 if e.label == "JOINS" or e.props.get("inferred") else 0
        d, source_alias, key = vertices[source]
        target_alias = vertices[target][1]
        alias = f"{source_alias}_{'_'.join(columns)}_{target_alias}"
        if len(alias) > _MAX_ALIAS:
            alias = f"{alias[:_MAX_ALIAS - 9]}_{hashlib.sha256(alias.encode()).hexdigest()[:8]}"
        # NO PROPERTIES: the default is every column of the table, withheld ones included.
        edges.append(f"    {table(d)} AS {element(alias)}\n      KEY ({cols(key)})\n"
                     f"      SOURCE KEY ({cols(key)}) REFERENCES {element(source_alias)} ({cols(key)})\n"
                     f"      DESTINATION KEY ({cols(columns)}) REFERENCES {element(target_alias)} ({cols(refs)})\n"
                     f"      NO PROPERTIES")
    if not vertices:
        raise ValueError("no table this caller may see has a primary key, so there is no graph to write")

    # Listed by name, for the same reason: the default would include withheld columns.
    lines = [f"    {table(d)} AS {element(alias)}\n      KEY ({cols(key)})\n"
             f"      PROPERTIES ({cols(c.name for c in d.visible_columns(principal))})"
             for d, alias, key in vertices.values()]
    head = ["-- Written by schemagate for review. schemagate does not run this.",
            "-- Needs Oracle 23ai or later and the CREATE PROPERTY GRAPH privilege."]
    if guessed:
        head.append(f"-- {guessed} edge(s) come from inferred foreign keys or view joins: check them.")
    head += [f"-- {n}" for n in notes]
    body = f"CREATE PROPERTY GRAPH {name}\n  VERTEX TABLES (\n" + ",\n".join(lines) + "\n  )"
    if edges:
        body += "\n  EDGE TABLES (\n" + ",\n".join(edges) + "\n  )"
    return "\n".join(head) + "\n" + body + ";\n"


# ------------------------------------------------------------------ pulling

@dataclass
class Proposal:
    """A concept the database implies, and what implies it."""
    name: str
    maps: List[str]
    evidence: str
    definition: Optional[str] = None


@dataclass
class PullReport:
    proposals: List[Proposal] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        out = [f"{len(self.proposals)} concept(s) proposed, {len(self.skipped)} skipped"]
        for p in self.proposals:
            meaning = f": {p.definition}" if p.definition else ""
            out.append(f"  {p.name!r} -> {', '.join(p.maps)}{meaning}  [{p.evidence}]")
        out += [f"  skipped: {s}" for s in self.skipped[:20]]
        if len(self.skipped) > 20:
            out.append(f"  ... and {len(self.skipped) - 20} more")
        return "\n".join(out)


def _line(text: Optional[str]) -> str:
    """One line. A comment goes into a `--` line of the prompt, and a newline would end that line."""
    return " ".join(str(text or "").split()).strip()


def _term(comment: str, own_name: str) -> Optional[str]:
    """The business term a short comment names, or None if it adds nothing."""
    words = comment.strip(" .:;,").strip()
    tokens = tokenize(words)
    if not tokens or len(tokens) > _TERM_WORDS:
        return None
    if words.lower() in _NOT_A_TERM_PHRASES or set(tokens) & _NOT_A_TERM or all(t in STOP for t in tokens):
        return None
    if set(phrase_key(words)) <= set(phrase_key(own_name.replace("_", " "))):
        return None                                      # "Customer id" on customer_id
    return words


def _is_key(doc, column) -> bool:
    return column.pk or any(column.name in fk.columns for fk in doc.foreign_keys)


def _phrase_name(name: str) -> str:
    return " ".join(name.replace("_", " ").split())


def pull_concepts(cat, dialect: Optional[str] = None) -> PullReport:
    """Propose concepts from comments and view SQL. See ``Catalog.pull_concepts``."""
    report = PullReport()
    found: Dict[Tuple[str, ...], Proposal] = {}
    clashes: Dict[Tuple[str, ...], str] = {}

    def offer(name: str, maps: List[str], evidence: str, definition: Optional[str] = None) -> None:
        key = phrase_key(name)
        if not key or key in clashes:
            return
        if key in cat.ontology._phrases:
            report.skipped.append(f"{name!r}: already in the vocabulary, left as it is")
            return
        old = found.get(key)
        if old is None:
            found[key] = Proposal(name, maps, evidence, definition)
        elif old.maps != maps or old.definition != definition:
            # One word, two meanings: a person has to say which.
            del found[key]
            clashes[key] = name
            report.skipped.append(f"{name!r}: means different things ({', '.join(old.maps + maps)})")

    docs = cat.objects()
    # Tables only: a view repeating a column does not give the name a second meaning.
    column_uses: Dict[str, int] = {}
    for d in docs:
        if d.kind != "VIEW":
            for c in d.columns:
                column_uses[c.name.lower()] = column_uses.get(c.name.lower(), 0) + 1

    for d in docs:
        comment = _line(d.description)
        term = _term(comment, d.name) if comment else None
        if term:
            offer(term, [d.qname], f"comment on {d.qname}")
        for c in d.columns:
            comment = _line(c.comment)
            if not comment or _is_key(d, c):
                continue
            ref = f"{d.qname}.{c.name}"
            term = _term(comment, c.name)
            if term:
                offer(term, [ref], f"comment on {ref}")
            elif len(tokenize(comment)) > _TERM_WORDS and len(comment) <= _MAX_TEXT:
                if column_uses.get(c.name.lower(), 0) > 1:
                    report.skipped.append(f"{ref}: other objects have a column {c.name!r}, so its "
                                          "name cannot stand for this comment")
                else:
                    offer(_phrase_name(c.name), [ref], f"comment on {ref}", comment)

    unread: List[str] = []
    for d in docs:
        if d.kind != "VIEW" or not d.definition:
            continue
        facts = read_view(d.definition, dialect)
        if facts is None:
            unread.append(d.name)
            continue
        if facts.where and len(facts.where) <= _MAX_TEXT:
            title = _phrase_name(_VIEW_AFFIX.sub("", d.name))
            offer(title, [d.qname], f"WHERE of view {d.qname}",
                  f"view {d.name} already applies: {facts.where}")
        for alias, expression in facts.computed:
            words = _phrase_name(alias)
            if len(expression) > _MAX_TEXT or not words or set(tokenize(words)) <= _GENERIC | STOP:
                continue
            definition = f"{alias} in view {d.name} is {expression}"
            if facts.where and len(facts.where) <= _MAX_TEXT:
                definition += f", only where {facts.where}"
            offer(words, [f"{d.qname}.{alias}"], f"computed column of view {d.qname}", definition)
    if unread:
        report.skipped.append(f"{len(unread)} view(s) not read (sqlglot missing, pip install "
                              f"'schemagate[graph]', or could not parse): {', '.join(sorted(unread)[:20])}")

    report.proposals = list(found.values())
    return report
