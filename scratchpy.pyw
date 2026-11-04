#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Version: V26.5
"""
ScratchPy - program in Python with Scratch-style blocks.

Run: python scratchpy.py (uses tkinter, included with Python)

Usage
    - Choose a category on the left, then drag blocks into the script area.
    - Blocks snap together; C-shaped blocks contain other blocks.
    - Round and hexagonal value blocks fit into slots in other blocks.
    - Slots accept Python expressions: 10, x + 1, "text" (put text in quotes).
    - Drag a block to the palette to delete it. Right-click to duplicate or delete.
    - The Python code on the right is editable: editing it rebuilds the blocks, and editing
        the blocks updates the code. Imports in the code add library categories to the palette.
    - Multi-select with Ctrl (or Shift) + click, or drag a selection rectangle on the workspace.
        Drag any selected block to move them all; Delete = delete, Ctrl+D = duplicate,
        Ctrl+C / Ctrl+V = copy / paste, Ctrl+A = select all, Esc = deselect.
    - Generated Python appears on the right; click Run to execute it (enter input
        in the bar at the bottom of the console).
"""
import ast
import codecs
import copy
import http.client
import importlib
import importlib.util
import inspect
import itertools
import json
import math
import os
import queue
import re
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, simpledialog, ttk

UPDATE_URL = "https://raw.githubusercontent.com/redcat67400-rgb/ScratchPy/program/scratchpy.pyw"
_VERSION_RE = re.compile(r"^\s*#\s*Version:\s*[Vv](\d+)\.(\d+)\s*$")


def source_version(source):
    for line in source.splitlines()[:5]:
        match = _VERSION_RE.match(line)
        if match:
            return "V%s.%s" % match.groups()
    return None


def version_key(version):
    if not version:
        return None
    match = re.fullmatch(r"[Vv](\d+)\.(\d+)", version)
    return tuple(map(int, match.groups())) if match else None


with open(__file__, "rb") as _source_file:
    APP_VERSION = source_version(_source_file.read(512).decode("utf-8-sig"))

# --------------------------------------------------------------------------
#  High DPI support for Windows
# --------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# --------------------------------------------------------------------------
#  Block definitions
# --------------------------------------------------------------------------
CATS = {
    "Control":    ("#FFAB19", "#CF8B17"),
    "Output":     ("#9966FF", "#774DCB"),
    "Variables":  ("#FF8C1A", "#DB6E00"),
    "Operators":  ("#59C059", "#389438"),
    "Functions":  ("#FF6680", "#E0405C"),
}
REPORTERS = ("reporter", "bool")

SPECS = {}
ORDER = {c: [] for c in CATS}


def _items(text):
    items, idx = [], 0
    for p in re.split(r"(\{\})", text):
        if p == "{}":
            items.append(("f", idx))
            idx += 1
        elif p.strip():
            items.append(("t", p.strip()))
    return items, idx


def spec(t, cat, shape, text, defaults=(), code="", alt=None, fn=None):
    items, n = _items(text)
    SPECS[t] = dict(cat=cat, shape=shape, items=items, nfields=n,
                    defaults=list(defaults), code=code, alt=alt, fn=fn,
                    label=" ".join(v for k, v in items if k == "t"))
    ORDER[cat].append(t)


C, A, V, O, F = "Control", "Output", "Variables", "Operators", "Functions"

spec("start", C, "hat", "when ▶ clicked")
spec("repeat", C, "c", "repeat {} times", ["10"], "for _ in range({0}):")
spec("for", C, "c", "for {} in {}", ["i", "range(10)"], "for {0} in {1}:")
spec("while", C, "c", "while {}", ["x < 10"], "while {0}:")
spec("forever", C, "c", "forever", [], "while True:")
spec("if", C, "c", "if {} then", ["x > 0"], "if {0}:")
spec("elif", C, "c", "else if {} then", ["x < 0"], "elif {0}:")
spec("else", C, "c", "else", [], "else:")
spec("ifelse", C, "celse", "if {} then", ["x > 0"], "if {0}:", alt="else")
ORDER[C].remove("ifelse")      # Legacy block: still readable in old projects, but hidden from the palette.
spec("break", C, "stack", "break loop", [], "break")
spec("continue", C, "stack", "next iteration", [], "continue")
spec("wait", C, "stack", "wait {} seconds", ["1"], "time.sleep({0})")
spec("comment", C, "stack", "# {}", ["comment"], "# {0}")
spec("print", A, "stack", "print {}", ['"Hello!"'], "print({0})")
spec("print_end", A, "stack", "print {} without newline", ['"..."'], 'print({0}, end="")')
spec("ask", A, "reporter", "ask {}", ['"Your name?"'], "input({0})")
spec("ask_num", A, "reporter", "ask for a number {}", ['"Your age?"'], "int(input({0}))")
# Variables
spec("set", V, "stack", "set {} to {}", ["x", "0"], "{0} = {1}")
spec("change", V, "stack", "add {} to {}", ["1", "x"], "{1} += {0}")
spec("var", V, "reporter", "variable {}", ["x"], "{0}")
spec("list_make", V, "stack", "create list {} with {}", ["items", "1, 2, 3"], "{0} = [{1}]")
spec("list_add", V, "stack", "append {} to list {}", ["4", "items"], "{1}.append({0})")
spec("list_set", V, "stack", "set item {} of {} to {}", ["0", "items", "5"], "{1}[{0}] = {2}")
spec("list_get", V, "reporter", "item {} of {}", ["0", "items"], "{1}[{0}]")
spec("list_len", V, "reporter", "length of {}", ["items"], "len({0})")
spec("add", O, "reporter", "{} + {}", ["1", "1"], "({0} + {1})")
spec("sub", O, "reporter", "{} - {}", ["1", "1"], "({0} - {1})")
spec("mul", O, "reporter", "{} × {}", ["2", "3"], "({0} * {1})")
spec("div", O, "reporter", "{} / {}", ["6", "3"], "({0} / {1})")
spec("idiv", O, "reporter", "{} div {}", ["7", "2"], "({0} // {1})")
spec("mod", O, "reporter", "{} modulo {}", ["7", "2"], "({0} % {1})")
spec("pow", O, "reporter", "{} to the power of {}", ["2", "8"], "({0} ** {1})")
spec("random", O, "reporter", "random integer from {} to {}", ["1", "10"], "random.randint({0}, {1})")
spec("round", O, "reporter", "round {}", ["3.14"], "round({0})")
spec("sqrt", O, "reporter", "square root of {}", ["16"], "math.sqrt({0})")
spec("abs", O, "reporter", "absolute value of {}", ["-5"], "abs({0})")
spec("join", O, "reporter", "join {} {}", ['"a"', '"b"'], "(str({0}) + str({1}))")
spec("str", O, "reporter", "string of {}", ["42"], "str({0})")
spec("int", O, "reporter", "integer of {}", ['"42"'], "int({0})")
spec("float", O, "reporter", "float of {}", ['"3.5"'], "float({0})")
spec("gt", O, "bool", "{} > {}", ["x", "5"], "({0} > {1})")
spec("lt", O, "bool", "{} < {}", ["x", "5"], "({0} < {1})")
spec("ge", O, "bool", "{} ≥ {}", ["x", "5"], "({0} >= {1})")
spec("le", O, "bool", "{} ≤ {}", ["x", "5"], "({0} <= {1})")
spec("eq", O, "bool", "{} = {}", ["x", "5"], "({0} == {1})")
spec("ne", O, "bool", "{} ≠ {}", ["x", "5"], "({0} != {1})")
spec("and", O, "bool", "{} and {}", ["x > 1", "x < 9"], "({0} and {1})")
spec("or", O, "bool", "{} or {}", ["x < 1", "x > 9"], "({0} or {1})")
spec("not", O, "bool", "not {}", ["x > 1"], "(not {0})")
spec("in", O, "bool", "{} in {}", ["3", "items"], "({0} in {1})")
spec("def", F, "c", "define {} ({})", ["greet", "name"], "def {0}({1}):",
     fn=lambda f: "def %s(%s):" % (expr(f[0]), raw(f[1])))
spec("call", F, "stack", "call {} ({})", ["greet", '"Alex"'], "{0}({1})",
     fn=lambda f: "%s(%s)" % (expr(f[0]), raw(f[1])))
spec("call_ret", F, "reporter", "result of {} ({})", ["square", "4"], "{0}({1})",
     fn=lambda f: "%s(%s)" % (expr(f[0]), raw(f[1])))
spec("return", F, "stack", "return {}", ["x"], "return {0}")
spec("pyline", F, "stack", "Python line {}", ["pass"], "{0}",
     fn=lambda f: f[0].rstrip() if isinstance(f[0], str) else expr(f[0]))
spec("pyc", F, "c", "Python block {}", ["try:"], "{0}",
     fn=lambda f: f[0].strip() if isinstance(f[0], str) else expr(f[0]))
spec("pyexpr", F, "reporter", "Python expression {}", ["1 + 1"], "({0})")

_meth = lambda f: "%s.%s(%s)" % (expr(f[0]), expr(f[1]), raw(f[2]))
spec("method", F, "stack", "{} . {} ({})", ["object", "method", ""], fn=_meth)
spec("method_ret", F, "reporter", "{} . {} ({})", ["object", "method", ""], fn=_meth)

# --------------------------------------------------------------------------
#  Libraries: each module function, class, or constant becomes a block
# --------------------------------------------------------------------------
def lib_color(name):
    """Return a library color based on its name:
    1. Take the first six letters (repeat from the start if needed).
    2. Convert each letter's rank (A=1 ... Z=26), divide by 26, and multiply by 16.
    3. Take the integer part, convert it to a hexadecimal digit, and combine as #RRGGBB.
    Example: tkinter -> T K I N T E -> 20 11 9 14 20 5 -> C 6 5 8 C 3 -> #C658C3."""
    letters = [c for c in unicodedata.normalize("NFD", name.lower()) if "a" <= c <= "z"]
    if not letters:
        return "#808080"
    out = "#"
    for i in range(6):
        n = ord(letters[i % len(letters)]) - 96
        out += "%X" % min(15, int(n / 26 * 16))      # Z would produce 16, so cap it at F.
    return out


LIBS = {}   # Module name -> block IDs.


def text_on(h):
    """Return whichever has better contrast against the background: white or black."""
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "black" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "white"


def _darken(h, k=0.78):
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % (int(r * k), int(g * k), int(b * k))


def _params(obj):
    try:
        sig = inspect.signature(obj)
    except Exception:
        return [("args", "var", True)]
    kinds = {inspect.Parameter.POSITIONAL_ONLY: "po", inspect.Parameter.POSITIONAL_OR_KEYWORD: "pk",
             inspect.Parameter.KEYWORD_ONLY: "kw", inspect.Parameter.VAR_POSITIONAL: "var"}
    out = []
    for p in sig.parameters.values():
        if p.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        kind = kinds[p.kind]
        out.append((p.name, kind, p.default is not inspect.Parameter.empty or kind == "var"))
    return out[:10]


def _call_fn(callname, params):
    def fn(fields):
        args, skipped = [], False
        for (name, kind, opt), v in zip(params, fields):
            val = raw(v)
            if kind == "var":
                if val:
                    args.append(val)
            elif kind == "kw":
                if val:
                    args.append("%s=%s" % (name, val))
                elif not opt:
                    args.append("%s=None" % name)
            elif val:
                args.append(val if (not skipped or kind == "po") else "%s=%s" % (name, val))
            elif opt:
                skipped = True
            else:
                args.append("None")
        return "%s(%s)" % (callname, ", ".join(args))
    return fn


def _add_lib_spec(t, modname, shape, label, params, callname, const=False):
    items = [("t", label)]
    for i, (name, kind, opt) in enumerate(params):
        items += [("t", ("*" if kind == "var" else "") + name), ("f", i)]
    SPECS[t] = dict(cat=modname, shape=shape, items=items, nfields=len(params),
                    defaults=[""] * len(params), code=callname if const else "",
                    alt=None, fn=None if const else _call_fn(callname, params), label=label)
    ORDER[modname].append(t)
    return t


def import_library(modname):
    """Import a Python module and create a block for each function, class, and constant."""
    modname = modname.strip()
    if not modname:
        raise ValueError("Module name cannot be empty.")
    if modname in LIBS:
        return 0
    mod = importlib.import_module(modname)
    names = getattr(mod, "__all__", None)
    names = [n for n in names if isinstance(n, str)] if names else \
        [n for n in dir(mod) if not n.startswith("_")]
    col = lib_color(modname)
    CATS[modname] = (col, _darken(col))
    ORDER[modname] = []
    ids = []
    for n in sorted(set(names)):
        try:
            obj = getattr(mod, n)
        except Exception:
            continue
        full = modname + "." + n
        if inspect.ismodule(obj):
            continue
        if inspect.isclass(obj) or inspect.isroutine(obj):
            params = _params(obj)
            shapes = [("r", "reporter")] if inspect.isclass(obj) else \
                [("s", "stack"), ("r", "reporter")]
            for suf, shape in shapes:
                label = full if suf == "r" else "call " + full
                ids.append(_add_lib_spec("lib:%s:%s" % (full, suf), modname, shape, label,
                                         params, full))
        elif isinstance(obj, (int, float, str, bool)):
            ids.append(_add_lib_spec("lib:%s:c" % full, modname, "reporter", full, [], full,
                                     const=True))
    LIBS[modname] = ids
    return len(ids)


def unload_library(mod):
    """Remove an imported library category and its blocks from the palette."""
    for t in LIBS.pop(mod, []):
        SPECS.pop(t, None)
    ORDER.pop(mod, None)
    CATS.pop(mod, None)


def unload_libraries():
    """Remove all imported library categories and blocks from the palette."""
    for mod in list(LIBS):
        unload_library(mod)


def used_libs(scripts):
    """Return modules used by at least one library block in the scripts."""
    used = set()

    def visit(b):
        sp = SPECS.get(b.t)
        if sp and b.t.startswith("lib:"):
            used.add(sp["cat"])
        for f in b.fields:
            if isinstance(f, Block):
                visit(f)
        for x in b.body + b.orelse:
            visit(x)

    for s in scripts:
        for b in s.blocks:
            visit(b)
    return used


_uid = itertools.count(1)


class Block:
    def __init__(self, t, fields=None, body=None, orelse=None):
        self.t = t
        self.uid = next(_uid)
        sp = SPECS[t]
        self.fields = list(fields) if fields is not None else list(sp["defaults"])
        while len(self.fields) < sp["nfields"]:
            self.fields.append("")
        self.body = list(body) if body else []
        self.orelse = list(orelse) if orelse else []

    @property
    def spec(self):
        return SPECS[self.t]

    @property
    def shape(self):
        return SPECS[self.t]["shape"]


class Script:
    def __init__(self, x, y, blocks):
        self.x, self.y, self.blocks = x, y, blocks


def to_dict(b):
    return {"t": b.t,
            "f": [to_dict(f) if isinstance(f, Block) else f for f in b.fields],
            "b": [to_dict(x) for x in b.body],
            "e": [to_dict(x) for x in b.orelse]}


def from_dict(d):
    if d["t"] not in SPECS:
        raise ValueError("Unknown block: %s" % d["t"])
    return Block(d["t"],
                 [from_dict(f) if isinstance(f, dict) else f for f in d["f"]],
                 [from_dict(x) for x in d.get("b", [])],
                 [from_dict(x) for x in d.get("e", [])])


# --------------------------------------------------------------------------
#  Python code generation
# --------------------------------------------------------------------------
def raw(v):
    if isinstance(v, Block):
        return expr(v)
    return str(v).strip()


def expr(v):
    if isinstance(v, Block):
        sp = v.spec
        if sp.get("fn"):
            return sp["fn"](v.fields)
        return sp["code"].format(*[expr(f) for f in v.fields])
    v = str(v).strip()
    return v if v else "None"


def stmt(b, ind, out):
    shape = b.shape
    pad = "    " * ind
    if shape == "hat":
        return
    if shape in REPORTERS:
        return
    out.append(pad + expr(b))
    if shape in ("c", "celse"):
        n = len(out)
        for x in b.body:
            stmt(x, ind + 1, out)
        if len(out) == n:
            out.append(pad + "    pass")
        if shape == "celse":
            out.append(pad + "else:")
            n = len(out)
            for x in b.orelse:
                stmt(x, ind + 1, out)
            if len(out) == n:
                out.append(pad + "    pass")


def generate(scripts, libs=(), paths=(), lines=()):
    runnable = [s for s in scripts if s.blocks and s.blocks[0].shape not in REPORTERS]
    defs = [s for s in runnable if s.blocks[0].t == "def"]
    rest = sorted([s for s in runnable if s not in defs], key=lambda s: (s.y, s.x))
    future = [l for l in lines if l.startswith("from __future__")]
    used = used_libs(scripts)
    out = []
    for l in (future + ["import sys, time, random, math"] +
              ["sys.path.insert(0, %r)" % d for d in paths] +
              ["import %s" % m for m in libs if m in used] +
              [l for l in lines if l not in future]):
        if l not in out:
            out.append(l)
    out.append("")
    head = len(out)
    for s in defs + rest:
        n = len(out)
        for b in s.blocks:
            stmt(b, 0, out)
        if len(out) > n:
            out.append("")
    if len(out) == head:
        out.append("# (no blocks yet)")
    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
#  Python -> blocks (opening an existing .py file)
# --------------------------------------------------------------------------
def _u(n):
    return ast.unparse(n)


def _header(n):
    m = copy.copy(n)
    m.body = [ast.Pass()]
    for f in ("orelse", "finalbody", "handlers", "decorator_list"):
        if hasattr(m, f):
            setattr(m, f, [])
    return _u(m).split("\n")[0]


def _lines(n):
    return [Block("pyline", [ln]) for ln in _u(n).split("\n")]


def _body(stmts):
    out = []
    for n in stmts:
        out.extend(_conv(n))
    return out


def _else(n):
    return [Block("else", [], _body(n.orelse))] if getattr(n, "orelse", None) else []


def _simple_args(c):
    return not c.keywords and not any(isinstance(a, ast.Starred) for a in c.args)


def _conv(n):
    B, t = Block, type(n)
    if t is ast.FunctionDef and not n.decorator_list and n.returns is None \
            and not getattr(n, "type_params", None):
        return [B("def", [n.name, _u(n.args)], _body(n.body))]
    if t in (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef):
        decos = [B("pyline", ["@" + _u(d)]) for d in n.decorator_list]
        return decos + [B("pyc", [_header(n)], _body(n.body))]
    if t is ast.For:
        it = n.iter
        if (isinstance(n.target, ast.Name) and n.target.id == "_" and isinstance(it, ast.Call)
                and _u(it.func) == "range" and len(it.args) == 1 and _simple_args(it)):
            head = B("repeat", [_u(it.args[0])], _body(n.body))
        else:
            head = B("for", [_u(n.target), _u(it)], _body(n.body))
        return [head] + _else(n)
    if t is ast.While:
        if isinstance(n.test, ast.Constant) and n.test.value is True:
            head = B("forever", [], _body(n.body))
        else:
            head = B("while", [_u(n.test)], _body(n.body))
        return [head] + _else(n)
    if t is ast.If:
        out = [B("if", [_u(n.test)], _body(n.body))]
        o = n.orelse
        while o:
            if len(o) == 1 and isinstance(o[0], ast.If):
                m = o[0]
                out.append(B("elif", [_u(m.test)], _body(m.body)))
                o = m.orelse
            else:
                out.append(B("else", [], _body(o)))
                break
        return out
    if t in (ast.With, ast.AsyncWith, ast.AsyncFor):
        return [B("pyc", [_header(n)], _body(n.body))] + _else(n)
    if t is ast.Try:
        out = [B("pyc", ["try:"], _body(n.body))]
        out += [B("pyc", [_header(h)], _body(h.body)) for h in n.handlers]
        out += _else(n)
        if n.finalbody:
            out.append(B("pyc", ["finally:"], _body(n.finalbody)))
        return out
    if t is ast.Break:
        return [B("break")]
    if t is ast.Continue:
        return [B("continue")]
    if t is ast.Return and n.value is not None:
        return [B("return", [_u(n.value)])]
    if t is ast.Assign and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
        return [B("set", [n.targets[0].id, _u(n.value)])]
    if t is ast.AugAssign and isinstance(n.target, ast.Name) and isinstance(n.op, ast.Add):
        return [B("change", [n.target.id, _u(n.value)])]
    if t is ast.Expr and isinstance(n.value, ast.Call):
        c, f = n.value, n.value.func
        if isinstance(f, ast.Name) and f.id == "print" and len(c.args) == 1 and _simple_args(c):
            return [B("print", [_u(c.args[0])])]
        if _u(f) == "time.sleep" and len(c.args) == 1 and _simple_args(c):
            return [B("wait", [_u(c.args[0])])]
        args = ", ".join([_u(a) for a in c.args] + [_u(k) for k in c.keywords])
        if isinstance(f, ast.Name):
            return [B("call", [f.id, args])]
        if isinstance(f, ast.Attribute):
            return [B("method", [_u(f.value), f.attr, args])]
    return _lines(n)


def python_to_blocks(src):
    """Convert Python source to blocks (raises SyntaxError for invalid code)."""
    return _body(ast.parse(src).body)


_HEADER = [("sys", None), ("time", None), ("random", None), ("math", None)]


def python_to_project(src, generated=False):
    """Like python_to_blocks, but top-level imports are not converted to blocks.
    Return (blocks, [(module, import_line), ...], paths).
    With generated=True, ignore the editor's standard import header and read
    sys.path.insert(0, '...') lines as project paths."""
    imports, paths, rest = [], [], []
    for n in ast.parse(src).body:
        if generated and isinstance(n, ast.Import) and [(a.name, a.asname) for a in n.names] == _HEADER:
            continue
        if (generated and isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                and _u(n.value.func) == "sys.path.insert" and len(n.value.args) == 2
                and isinstance(n.value.args[1], ast.Constant) and isinstance(n.value.args[1].value, str)):
            paths.append(n.value.args[1].value)
            continue
        if isinstance(n, ast.Import):
            for a in n.names:
                imports.append((a.name, _u(ast.Import(names=[a]))))
        elif isinstance(n, ast.ImportFrom) and not n.level and n.module:
            imports.append((n.module, _u(n)))
        else:
            rest.append(n)
    return _body(rest), imports, paths


def count_blocks(L):
    return sum(1 + count_blocks(b.body) + count_blocks(b.orelse) for b in L)


def local_imports(src, folder):
    """Return imported modules that exist as files beside the source file."""
    found = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return found
    for n in ast.walk(tree):
        names = [a.name for a in n.names] if isinstance(n, ast.Import) else \
            ([n.module] if isinstance(n, ast.ImportFrom) and n.module and not n.level else [])
        for m in names:
            top = m.split(".")[0]
            if os.path.exists(os.path.join(folder, top + ".py")) or \
                    os.path.isdir(os.path.join(folder, top)):
                found.append(top)
    return found


# --------------------------------------------------------------------------
#  Render blocks on a canvas
# --------------------------------------------------------------------------
def _flat(pts):
    return [c for p in pts for c in p]


def _notch_r(x0, y, x1):      # Top edge (inward notch), from left to right.
    return [(x0 + 14, y), (x0 + 18, y + 4), (x0 + 30, y + 4), (x0 + 34, y), (x1, y)]


def _bump_l(x0, y):           # Bottom edge (outward tab), from right to left.
    return [(x0 + 34, y), (x0 + 30, y + 4), (x0 + 18, y + 4), (x0 + 14, y), (x0, y)]


class Renderer:
    GAP, PADX, ROWH, FH = 6, 10, 34, 22
    IND, EMPTY, FOOT, MID, HAT = 24, 22, 24, 28, 14

    def __init__(self, canvas, font, place_entry=None):
        self.c = canvas
        self.font = font
        self.place_entry = place_entry
        self.lh = font.metrics("linespace")
        self.force_ctx = None
        self.selected = set()
        self.reset()

    def reset(self):
        self.memo = {}
        self.hits = []      # (x, y, w, h, block, context)
        self.snaps = []     # (x, y, list, index, dragging)
        self.slots = []     # (x, y, w, h, parent, index, dragging)
        self.in_drag = False

    def _ol(self, b, dark):
        """Return a thick white outline for selected blocks."""
        return ("#FFFFFF", 3) if b.uid in self.selected else (dark, 1)

    def find(self, x, y):
        for h in reversed(self.hits):
            if h[0] <= x <= h[0] + h[2] and h[1] <= y <= h[1] + h[3]:
                return h
        return None

    def _hit(self, x, y, w, h, b, ctx):
        self.hits.append((x, y, w, h, b, self.force_ctx or ctx))

    # ---- measurements ----
    def fsize(self, v):
        if isinstance(v, Block):
            return self.rsize(v)
        return (max(28, self.font.measure(v) + 18), self.FH)

    def row(self, b):
        key = ("row", b.uid)
        if key in self.memo:
            return self.memo[key]
        w = h = 0
        for n, (k, v) in enumerate(b.spec["items"]):
            if k == "t":
                iw, ih = self.font.measure(v), self.lh
            else:
                iw, ih = self.fsize(b.fields[v])
            w += iw + (self.GAP if n else 0)
            h = max(h, ih)
        self.memo[key] = (w, h)
        return w, h

    def rsize(self, b):
        w, h = self.row(b)
        pad = 14 if b.shape == "bool" else 10
        return (w + 2 * pad, max(28, h + 8))

    def hsize(self, b):
        w, h = self.row(b)
        minw = 100 if b.shape == "hat" else (90 if b.shape in ("c", "celse") else 60)
        W = max(w + 2 * self.PADX, minw)
        H = max(self.ROWH, h + 12)
        if b.shape == "hat":
            H += self.HAT
        return W, H

    def lsize(self, L):
        return sum(self.ssize(b)[1] for b in L)

    def ssize(self, b):
        key = ("s", b.uid)
        if key in self.memo:
            return self.memo[key]
        W, H = self.hsize(b)
        if b.shape == "c":
            H += max(self.lsize(b.body), self.EMPTY) + self.FOOT
        elif b.shape == "celse":
            H += (max(self.lsize(b.body), self.EMPTY) + self.MID +
                  max(self.lsize(b.orelse), self.EMPTY) + self.FOOT)
        self.memo[key] = (W, H)
        return W, H

    # ---- drawing ----
    def draw_row(self, b, x, y, h):
        cx = x
        for n, (k, v) in enumerate(b.spec["items"]):
            if n:
                cx += self.GAP
            if k == "t":
                self.c.create_text(cx, y + h / 2, text=v, anchor="w",
                                   fill=text_on(CATS[b.spec["cat"]][0]),
                                   font=self.font, tags=("shape", "txt"))
                cx += self.font.measure(v)
                continue
            val = b.fields[v]
            iw, ih = self.fsize(val)
            iy = y + (h - ih) / 2
            self.slots.append((cx, iy, iw, ih, b, v, self.in_drag))
            if isinstance(val, Block):
                self.draw_reporter(val, cx, iy, ("slot", b, v))
            elif self.place_entry:
                self.place_entry(b, v, cx, iy, iw, ih)
            else:
                self.c.create_rectangle(cx, iy, cx + iw, iy + ih, fill="white",
                                        outline="", tags="shape")
                self.c.create_text(cx + iw / 2, iy + ih / 2, text=val, fill="#575E75",
                                   font=self.font, tags=("shape", "txt"))
            cx += iw

    def draw_reporter(self, b, x, y, ctx):
        w, h = self.rsize(b)
        col, dark = CATS[b.spec["cat"]]
        ol, wd = self._ol(b, dark)
        if b.shape == "bool":
            pts = [x + h / 2, y, x + w - h / 2, y, x + w, y + h / 2,
                   x + w - h / 2, y + h, x + h / 2, y + h, x, y + h / 2]
            self.c.create_polygon(pts, fill=col, outline=ol, width=wd, tags="shape")
        else:
            r = min(h / 2, 14)
            pts = [x + r, y, x + w - r, y, x + w, y, x + w, y + r, x + w, y + h - r,
                   x + w, y + h, x + w - r, y + h, x + r, y + h, x, y + h,
                   x, y + h - r, x, y + r, x, y]
            self.c.create_polygon(pts, smooth=True, fill=col, outline=ol, width=wd, tags="shape")
        self._hit(x, y, w, h, b, ctx)
        self.draw_row(b, x + (14 if b.shape == "bool" else 10), y, h)

    def draw_list(self, L, x, y):
        for i, b in enumerate(L):
            self.snaps.append((x, y, L, i, self.in_drag))
            self.draw_stmt(b, x, y, L, i)
            y += self.ssize(b)[1]
        self.snaps.append((x, y, L, len(L), self.in_drag))
        return y

    def draw_stmt(self, b, x, y, L, i):
        W, Hh = self.hsize(b)
        col, dark = CATS[b.spec["cat"]]
        ol, wd = self._ol(b, dark)
        shape = b.shape
        hat = self.HAT if shape == "hat" else 0
        ctx = ("list", L, i)
        if shape in ("stack", "hat"):
            if hat:
                top = [(x, y + 14), (x + 10, y + 5), (x + 28, y), (x + 62, y),
                       (x + 84, y + 5), (x + 94, y + 14), (x + W, y + 14)]
            else:
                top = [(x, y)] + _notch_r(x, y, x + W)
            pts = top + [(x + W, y + Hh)] + _bump_l(x, y + Hh)
            self.c.create_polygon(_flat(pts), fill=col, outline=ol, width=wd, tags="shape")
            self._hit(x, y, W, Hh, b, ctx)
            self.draw_row(b, x + self.PADX, y + hat, Hh - hat)
            return
        # C-shaped blocks (one or two compartments).
        arms = [(Hh, b.body)]
        if shape == "celse":
            arms.append((self.MID, b.orelse))
        pts = [(x, y)] + _notch_r(x, y, x + W)
        cur = y
        placed = []
        for hh, body in arms:
            hb = cur + hh
            bb = hb + max(self.lsize(body), self.EMPTY)
            pts += [(x + W, hb)] + _bump_l(x + self.IND, hb)
            pts += [(x + self.IND, bb)] + _notch_r(x + self.IND, bb, x + W)
            placed.append((cur, hh, hb, body))
            cur = bb
        pts += [(x + W, cur + self.FOOT)] + _bump_l(x, cur + self.FOOT)
        self.c.create_polygon(_flat(pts), fill=col, outline=ol, width=wd, tags="shape")
        self._hit(x, y, W, Hh, b, ctx)
        self.draw_row(b, x + self.PADX, y, Hh)
        if shape == "celse":
            my = placed[1][0]
            self.c.create_text(x + self.PADX, my + self.MID / 2, text=b.spec["alt"],
                               anchor="w", fill=text_on(col), font=self.font, tags=("shape", "txt"))
            self._hit(x, my, W, self.MID, b, ctx)
        self._hit(x, cur, W, self.FOOT, b, ctx)
        for _, _, hb, body in placed:
            self.draw_list(body, x + self.IND, hb)


def resource(name):
    """Return the path to a bundled resource (including in a PyInstaller executable)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def system_python():
    for name in ("python", "python3"):
        exe = shutil.which(name)
        if exe and "windowsapps" not in exe.lower():
            return exe
    return None


def python_command(path):
    """Build the command that runs generated code (system Python or the frozen executable)."""
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-u", path]
    py = system_python()
    return [py, "-u", path] if py else [sys.executable, "--run", path]


# --------------------------------------------------------------------------
#  AI assistant: ScratchPy server client
# --------------------------------------------------------------------------
ASSISTANT_URL = "https://scratchpy-server.onrender.com/v1/ask"
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash-lite"]
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".scratchpy", "config.json")


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1)
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except OSError:
            pass
    except OSError:
        pass


class AssistantError(Exception):
    pass


def _server_error_text(code, raw):
    detail = ""
    try:
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict):
            value = payload.get("detail") or payload.get("error")
            if isinstance(value, str):
                detail = value.strip()
            elif isinstance(value, dict):
                detail = str(value.get("message", "")).strip()
            elif value is not None:
                detail = str(value).strip()
    except (UnicodeDecodeError, ValueError):
        pass
    hints = {
        404: "The assistant endpoint was not found.",
        429: "The assistant service is receiving too many requests. Try again later.",
        500: "The assistant server encountered an error. Try again later.",
        502: "The assistant server is temporarily unavailable.",
        503: "The assistant service is temporarily unavailable. Try again later.",
    }
    message = hints.get(code, "The assistant server returned an HTTP error.")
    if detail:
        message += " " + detail[:400]
    return "HTTP %d: %s" % (code, message)


def ask_assistant(model, messages, code, console, timeout=120):
    """Send a chat request to the ScratchPy server and return its response text."""
    if model not in DEFAULT_MODELS:
        raise AssistantError("Please choose one of the available assistant models.")
    body = {"model": model, "messages": messages, "code": code, "console": console}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        ASSISTANT_URL, data=data, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as ex:
        try:
            raw = ex.read()
        except Exception:
            raw = b""
        raise AssistantError(_server_error_text(ex.code, raw)) from None
    except (socket.timeout, TimeoutError):
        raise AssistantError(
            "The ScratchPy assistant server took too long to respond. Please try again.") from None
    except urllib.error.URLError as ex:
        if isinstance(ex.reason, (socket.timeout, TimeoutError)):
            raise AssistantError(
                "The ScratchPy assistant server took too long to respond. Please try again.") from None
        raise AssistantError(
            "Could not connect to the ScratchPy assistant server. Check your internet connection "
            "and try again.") from None
    except http.client.HTTPException:
        raise AssistantError(
            "The ScratchPy server returned an invalid HTTP response. Please try again.") from None
    except OSError:
        raise AssistantError(
            "A network error interrupted the request to the ScratchPy assistant server.") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AssistantError("The ScratchPy server returned an invalid JSON response.") from None
    if not isinstance(payload, dict):
        raise AssistantError("The ScratchPy server returned an unexpected response format.")
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise AssistantError("The ScratchPy server response did not contain any assistant text.")
    return text


def build_messages(history):
    """Convert chat history to the role/text format accepted by the server."""
    out = [{"role": role, "text": text} for role, text in history
           if role in ("user", "model")]
    out = out[-30:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


_FENCE = re.compile(r"```([\w+#.-]*)[ \t]*\n(.*?)(?:```|\Z)", re.S)
_INLINE = re.compile(r"(\*\*[^*\n]+\*\*|`[^`\n]+`)")


def chat_segments(text):
    """Split a response into ("text", text) and ("code", language, code) segments."""
    out, pos = [], 0
    for m in _FENCE.finditer(text):
        if m.start() > pos:
            out.append(("text", text[pos:m.start()]))
        out.append(("code", m.group(1).lower(), m.group(2).rstrip("\n")))
        pos = m.end()
    if pos < len(text):
        out.append(("text", text[pos:]))
    return out


def md_line(line):
    """Return text fragments and formatting tags for one Markdown line."""
    m = re.match(r"^(\s*)([*-]) +(.*)$", line)
    if m:
        line = m.group(1) + "• " + m.group(3)
    m = re.match(r"^#{1,6}\s+(.*)$", line)
    if m:
        return [(m.group(1), "bold")]
    out = []
    for part in _INLINE.split(line):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], "bold"))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out.append((part[1:-1], "icode"))
        else:
            out.append((part, None))
    return out


def last_python_block(text):
    """Return the last valid ```python block in a response, or None."""
    best = None
    for seg in chat_segments(text):
        if seg[0] == "code" and seg[1] in ("python", "py", "python3") and seg[2].strip():
            best = seg[2]
    if best is None:
        return None
    try:
        ast.parse(best)
    except SyntaxError:
        return None
    return best


# --------------------------------------------------------------------------
#  Application
# --------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        root.title("ScratchPy - program in Python with blocks")
        
        # Adapt the window to the screen size.
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = min(max(int(sw * 0.85), 1000), sw)
        h = min(max(int(sh * 0.85), 650), sh)
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        root.minsize(900, 600)
        try:                                   # Maximize the window while keeping the taskbar visible.
            root.state("zoomed")               # Windows
        except tk.TclError:
            try:
                root.attributes("-zoomed", True)   # Linux
            except tk.TclError:
                pass
        
        self.cfg = load_config()
        if "gemini_key" in self.cfg:
            self.cfg.pop("gemini_key")
            save_config(self.cfg)
        self.set_icon()
        self.setup_theme()
        base = tkfont.nametofont("TkDefaultFont")
        self.font = tkfont.Font(family=base.actual("family"), size=10, weight="bold")
        self.efont = tkfont.Font(family=base.actual("family"), size=10)
        self.zfont = tkfont.Font(family=base.actual("family"), size=10, weight="bold")
        self.zefont = tkfont.Font(family=base.actual("family"), size=10)
        self.zoom = 1.0
        self.scripts = []
        self.saved_state = None
        app_file = sys.executable if getattr(sys, "frozen", False) else __file__
        self.app_folder = os.path.dirname(os.path.abspath(app_file))
        self.autosave_path = os.path.join(self.app_folder, "save", "autosave.json")
        self.autosave_interval = 60_000
        self.autosaved_state = None
        self.autosave_job = None
        self.libs = []
        self.paths = []
        self.import_lines = []
        self.drag = None
        self.sel = set()          # Selected block IDs.
        self.band = None          # Active selection rectangle.
        self.code_error = None    # Syntax error in edited code (None means valid).
        self._code_job = None
        self._drag_job = None
        self.ai_history = []      # Assistant conversation: ("user" | "model", text).
        self.ai_busy = False
        self.ai_token = 0
        self.ai_q = queue.Queue()
        self.ai_backup = None
        self.clip = []
        self.paste_n = 0
        self.entries = {}
        self.used = set()
        self.inside = False
        self.proc = None
        self.token = 0
        self.q = queue.Queue(maxsize=64)      # Bound the queue to slow overly chatty programs.
        self.update_q = queue.Queue(maxsize=1)
        self.update_payload = None
        self.update_checking = False
        self.closing = False
        self.cat = "Control"
        self._job = None
        self.build_ui()
        self.show_palette(self.cat)
        self.set_scripts([])          # Start with an empty workspace.
        self.mark_saved()
        self.autosaved_state = self.project_state()
        
        # Position the split panes after the window is drawn.
        root.after(800, self._init_paned_positions)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(40, self.poll)
        root.after(100, self.ai_poll)
        root.after(1500, self.check_for_updates)
        root.after(1000, self.restore_autosave)
        self.autosave_job = root.after(self.autosave_interval, self.autosave_tick)

    def check_for_updates(self):
        if sys.platform != "win32" or getattr(sys, "frozen", False) or self.update_checking:
            return
        self.update_checking = True

        def check():
            try:
                req = urllib.request.Request(
                    UPDATE_URL,
                    headers={"User-Agent": "ScratchPy updater",
                             "Range": "bytes=0-511"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    remote_version = source_version(
                        response.read(512).decode("utf-8-sig"))
                remote_key = version_key(remote_version)
                current_key = version_key(APP_VERSION)
                if remote_key is None or current_key is None or remote_key <= current_key:
                    return

                req = urllib.request.Request(
                    UPDATE_URL, headers={"User-Agent": "ScratchPy updater"})
                with urllib.request.urlopen(req, timeout=8) as response:
                    payload = response.read(5 * 1024 * 1024 + 1)
                if len(payload) > 5 * 1024 * 1024:
                    return
                source = payload.decode("utf-8-sig")
                if source_version(source) != remote_version:
                    return
                compile(source, "scratchpy.pyw", "exec")
                self.update_q.put_nowait(payload)
            except Exception:
                pass
            finally:
                self.update_checking = False

        threading.Thread(target=check, daemon=True).start()
        self.root.after(200, self.poll_update)

    def poll_update(self):
        if self.closing:
            return
        try:
            payload = self.update_q.get_nowait()
        except queue.Empty:
            if self.update_checking:
                self.root.after(200, self.poll_update)
            return
        if messagebox.askyesno(
                "Update available",
                "A newer ScratchPy version is available on GitHub. "
                "Install it now?", parent=self.root):
            self.update_payload = payload
            self.on_close()

    def install_update(self):
        if self.update_payload is None:
            return True
        folder = None
        try:
            target = os.path.abspath(__file__)
            folder = tempfile.mkdtemp(prefix="scratchpy-update-")
            staged = os.path.join(folder, "scratchpy.pyw")
            updater = os.path.join(folder, "update.ps1")
            with open(staged, "wb") as f:
                f.write(self.update_payload)

            def ps_quote(value):
                return "'" + value.replace("'", "''") + "'"

            script = (
                "$processId = %d\n"
                "while (Get-Process -Id $processId -ErrorAction SilentlyContinue) { "
                "Start-Sleep -Seconds 1 }\n"
                "Copy-Item -LiteralPath %s -Destination %s -Force\n"
                "if ($?) { Start-Process -FilePath %s "
                "-ArgumentList ('\"' + %s + '\"') }\n"
                "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force\n"
                "Remove-Item -LiteralPath %s -Recurse -Force\n"
            ) % (os.getpid(), ps_quote(staged), ps_quote(target),
                 ps_quote(sys.executable), ps_quote(target), ps_quote(folder))
            with open(updater, "w", encoding="utf-8") as f:
                f.write(script)
            flags = 0x00000008 | 0x08000000 if sys.platform == "win32" else 0
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", updater], creationflags=flags,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            return True
        except OSError as ex:
            if folder:
                shutil.rmtree(folder, ignore_errors=True)
            messagebox.showerror("Update", "Could not start the updater:\n%s" % ex,
                                 parent=self.root)
            return False

    def _init_paned_positions(self):
        """Set initial panel positions based on the screen size."""
        try:
            w = self.main_paned.winfo_width()
            if w > 200:
                right_width = max(300, int(w * 0.23))
                self.main_paned.sash_place(0, 320, 0)
                self.main_paned.sash_place(1, w - right_width, 0)
            
            h = self.right_paned.winfo_height()
            if h > 200:
                self.right_paned.sash_place(0, 0, int(h / 3))
                self.right_paned.sash_place(1, 0, int(h * 2 / 3))
        except Exception:
            pass

    # ---------- window icon ----------
    def set_icon(self):
        """Set the window and taskbar icons."""
        log = os.path.join(tempfile.gettempdir(), "scratchpy_icon.log")

        def note(msg):
            try:
                with open(log, "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass

        try:
            open(log, "w").close()
        except Exception:
            pass
        ico, png = resource("scratchpy_logo.ico"), resource("scratchpy_logo.png")
        root = self.root
        if sys.platform == "win32":
            try:
                root.iconbitmap(default=ico)
            except Exception as ex:
                note("iconbitmap failed: %r" % ex)
        try:
            img = tk.PhotoImage(file=png)
            k = max(1, img.width() // 128)
            self.logo = img.subsample(k) if k > 1 else img
            root.iconphoto(True, self.logo)
        except Exception as ex:
            note("iconphoto failed: %r" % ex)

    # ---------- dark theme ----------
    BG, BG2, EDIT = "#1e2027", "#2b2e38", "#15171c"
    FG, MUTED, ACCENT, BORDER = "#e4e6eb", "#9aa0aa", "#4C97FF", "#3a3e4a"

    def setup_theme(self):
        """Set the dark theme and use Calibri (or Arial as a fallback)."""
        root = self.root
        self.theme_name = self.cfg.get("theme", "dark")
        if self.theme_name not in ("light", "dark"):
            self.theme_name = "dark"
        BG, BG2, EDIT, FG, MUTED, ACCENT, BORDER = (self.BG, self.BG2, self.EDIT, self.FG,
                                                    self.MUTED, self.ACCENT, self.BORDER)
        fams = {f.lower(): f for f in tkfont.families(root)}
        fam = next((fams[f] for f in ("calibri", "arial") if f in fams), None)
        size = 11 if fam and fam.lower() == "calibri" else 10
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkCaptionFont", "TkTooltipFont", "TkIconFont"):
            try:
                f = tkfont.nametofont(name)
                f.configure(size=size, **({"family": fam} if fam else {}))
            except tk.TclError:
                pass
        try:      # Keep code in a monospace font.
            fx = tkfont.nametofont("TkFixedFont")
            mono = next((fams[f] for f in ("consolas", "cascadia mono", "courier new") if f in fams), None)
            fx.configure(size=10, **({"family": mono} if mono else {}))
        except tk.TclError:
            pass

        root.configure(bg=BG)
        for k, v in (("Background", BG), ("Foreground", FG), ("highlightBackground", BG),
                     ("highlightColor", ACCENT), ("Menu.background", BG2), ("Menu.foreground", FG),
                     ("Menu.activeBackground", ACCENT), ("Menu.activeForeground", "white"),
                     ("Menu.relief", "flat"), ("Menu.borderWidth", 0),
                     ("PanedWindow.background", "#12141a"), ("Entry.background", EDIT),
                     ("Entry.foreground", FG), ("Entry.insertBackground", FG),
                     ("Entry.selectBackground", "#3b4261"), ("Entry.selectForeground", FG),
                     ("TCombobox*Listbox.background", EDIT), ("TCombobox*Listbox.foreground", FG),
                     ("TCombobox*Listbox.selectBackground", ACCENT),
                     ("TCombobox*Listbox.selectForeground", "white")):
            root.option_add("*" + k, v)

        st = ttk.Style(root)
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        st.configure(".", background=BG, foreground=FG, fieldbackground=EDIT, bordercolor=BORDER,
                     lightcolor=BG2, darkcolor=BG2, troughcolor=BG, focuscolor=BG, insertcolor=FG)
        st.configure("TButton", background=BG2, foreground=FG, padding=(10, 4), relief="flat",
                     borderwidth=1, bordercolor=BORDER)
        st.map("TButton", background=[("pressed", "#454b58"), ("active", "#373b47")],
               foreground=[("disabled", MUTED)], bordercolor=[("active", ACCENT)])
        st.configure("Run.TButton", background="#2e7d4f", bordercolor="#58a879")
        st.map("Run.TButton", background=[("pressed", "#276b43"), ("active", "#37955d")])
        st.configure("Stop.TButton", background="#8f3b3b", bordercolor="#c06161")
        st.map("Stop.TButton", background=[("pressed", "#7a3030"), ("active", "#a84646")])
        st.configure("TEntry", fieldbackground=EDIT, foreground=FG, padding=4, bordercolor=BORDER,
                     insertcolor=FG)
        st.map("TEntry", bordercolor=[("focus", ACCENT)])
        st.configure("TCombobox", fieldbackground=EDIT, background=BG2, foreground=FG, padding=3,
                     arrowcolor=FG, bordercolor=BORDER, selectbackground="#3b4261", selectforeground=FG)
        st.map("TCombobox", bordercolor=[("focus", ACCENT)], fieldbackground=[("readonly", EDIT)],
               foreground=[("readonly", FG)])
        st.configure("TScrollbar", background="#3a3e4a", troughcolor=BG, bordercolor=BG,
                     arrowcolor=FG, lightcolor="#3a3e4a", darkcolor="#3a3e4a", gripcount=0,
                     arrowsize=13, relief="flat")
        st.map("TScrollbar", background=[("active", "#4f5565"), ("pressed", "#5d6475")])
        st.configure("TSeparator", background=BORDER)
        self.style = st
        self.apply_theme()
        return fam, size

    def apply_theme(self):
        dark = self.theme_name == "dark"
        colors = ({"BG": "#1e2027", "BG2": "#2b2e38", "EDIT": "#15171c",
                   "FG": "#e4e6eb", "MUTED": "#9aa0aa", "ACCENT": "#4C97FF",
                   "BORDER": "#3a3e4a", "PAL": "#262932", "WS": "#1b1d23",
                   "CONSOLE": "#101216", "CONSOLE_FG": "#d6dae0"} if dark else
                  {"BG": "#f3f5f8", "BG2": "#e5e9ef", "EDIT": "#ffffff",
                   "FG": "#20242b", "MUTED": "#626b78", "ACCENT": "#2563eb",
                   "BORDER": "#c5ccd6", "PAL": "#f7f8fa", "WS": "#edf1f5",
                   "CONSOLE": "#e4e8ed", "CONSOLE_FG": "#20242b"})
        colors["BUTTON_BORDER"] = "#596171" if dark else "#98a2b1"
        self.theme_colors = colors
        self.BG, self.BG2, self.EDIT = colors["BG"], colors["BG2"], colors["EDIT"]
        self.FG, self.MUTED = colors["FG"], colors["MUTED"]
        self.ACCENT, self.BORDER = colors["ACCENT"], colors["BORDER"]
        self.root.configure(bg=self.BG)
        for key, value in (("TCombobox*Listbox.background", self.EDIT),
                           ("TCombobox*Listbox.foreground", self.FG),
                           ("TCombobox*Listbox.selectBackground", self.ACCENT),
                           ("TCombobox*Listbox.selectForeground", "white")):
            self.root.option_add("*" + key, value)
        st = self.style
        st.configure(".", background=self.BG, foreground=self.FG,
                     fieldbackground=self.EDIT, bordercolor=self.BORDER,
                     lightcolor=self.BG2, darkcolor=self.BG2, troughcolor=self.BG,
                     focuscolor=self.BG, insertcolor=self.FG)
        st.configure("TButton", background=self.BG2, foreground=self.FG,
                   relief="solid", borderwidth=1, bordercolor=colors["BUTTON_BORDER"])
        st.map("TButton", background=[("pressed", self.BORDER), ("active", self.BG2)],
               foreground=[("disabled", self.MUTED)],
               bordercolor=[("active", self.ACCENT), ("pressed", self.ACCENT)])
        st.configure("TEntry", fieldbackground=self.EDIT, foreground=self.FG,
                     bordercolor=self.BORDER, insertcolor=self.FG)
        st.configure("TCombobox", fieldbackground=self.EDIT, background=self.BG2,
                     foreground=self.FG, arrowcolor=self.FG, bordercolor=self.BORDER)
        st.map("TCombobox", fieldbackground=[("readonly", self.EDIT)],
               foreground=[("readonly", self.FG)],
               selectbackground=[("readonly", self.ACCENT)],
               selectforeground=[("readonly", "white")])
        st.configure("TScrollbar", background=self.BG2, troughcolor=self.BG,
                     bordercolor=self.BG, arrowcolor=self.FG, lightcolor=self.BG2,
                     darkcolor=self.BG2)
        st.configure("TSeparator", background=self.BORDER)
        st.configure("TNotebook", background=self.BG, bordercolor=self.BORDER)
        st.configure("TNotebook.Tab", background=self.BG2, foreground=self.MUTED,
                     padding=(14, 7))
        st.map("TNotebook.Tab", background=[("selected", self.BG)],
               foreground=[("selected", self.FG)])
        st.configure("TRadiobutton", background=self.BG2, foreground=self.FG)
        st.map("TRadiobutton", background=[("active", self.BG2)],
               foreground=[("disabled", self.MUTED)])

        category_labels = set(getattr(self, "cat_labels", {}).values())

        def recolor(parent):
            for widget in parent.winfo_children():
                if widget in category_labels:
                    continue
                if isinstance(widget, tk.Frame):
                    widget.configure(bg=self.BG2)
                elif isinstance(widget, tk.Label):
                    widget.configure(bg=self.BG2, fg=self.FG)
                elif isinstance(widget, tk.PanedWindow):
                    widget.configure(bg=self.BG)
                elif isinstance(widget, tk.Canvas):
                    bg = colors["PAL"] if widget is getattr(self, "pal", None) else colors["WS"]
                    widget.configure(bg=bg)
                recolor(widget)

        recolor(self.root)
        if hasattr(self, "code"):
            self.code.configure(bg=self.EDIT, fg=self.FG, insertbackground=self.FG,
                                selectbackground="#3b4261" if dark else "#cbdcff")
            self.code.tag_configure("errline", background="#5a1d1d" if dark else "#ffe0df")
            self.console.configure(bg=colors["CONSOLE"], fg=colors["CONSOLE_FG"])
            self.console.tag_configure("err", foreground="#ff8a80" if dark else "#b42318")
            self.ai_chat.configure(bg=self.EDIT, fg=colors["CONSOLE_FG"])
            for tag, light, dark_color in (
                    ("user", "#26733b", "#a6e3a1"), ("bot", "#2459a6", "#89b4fa"),
                    ("err", "#b42318", "#f38ba8"), ("info", "#626b78", "#9399b2"),
                    ("who", "#735c00", "#f9e2af"), ("undo", "#735c00", "#f9e2af")):
                self.ai_chat.tag_configure(tag, foreground=dark_color if dark else light)
            self.ai_chat.tag_configure("icode", background="#313244" if dark else "#e5e9ef",
                                       foreground="#f5e0dc" if dark else "#30343b")
            self.ai_chat.tag_configure("code", background="#11111b" if dark else "#e5e9ef",
                                       foreground="#f5e0dc" if dark else "#30343b")

    def set_theme(self, theme):
        if theme not in ("light", "dark") or theme == self.theme_name:
            return
        self.theme_name = theme
        self.cfg["theme"] = theme
        save_config(self.cfg)
        if hasattr(self, "settings_theme_var"):
            self.settings_theme_var.set(theme)
        self.apply_theme()

    # ---------- interface ----------
    def build_ui(self):
        root = self.root
        bar = tk.Frame(root, padx=8, pady=6)
        bar.pack(side="top", fill="x")
        tk.Frame(root, height=1, bg=self.BORDER).pack(side="top", fill="x")
        for item in (("▶ Run", self.run), ("■ Stop", self.stop), None,
                  ("New", self.new), ("Open (.py or project)…", self.open_file),
                  ("Save…", self.save_file), ("Export .py…", self.export_py),
                  None, ("Import a library…", self.import_lib),
                  ("Example", self.load_example)):
            if item is None:
                ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
                continue
            text, cmd = item
            sty = "Run.TButton" if cmd == self.run else "Stop.TButton" if cmd == self.stop else "TButton"
            ttk.Button(bar, text=text, command=cmd, style=sty).pack(side="left", padx=2)
        zf = tk.Frame(bar)
        zf.pack(side="right")
        self.zoom_var = tk.StringVar(value="100 %")
        ttk.Button(zf, text="+", width=3, command=lambda: self.zoom_by(1.25)).pack(side="right", padx=2)
        ttk.Button(zf, textvariable=self.zoom_var, width=6,
                   command=lambda: self.set_zoom(1.0)).pack(side="right")
        ttk.Button(zf, text="−", width=3, command=lambda: self.zoom_by(0.8)).pack(side="right", padx=2)
        tk.Label(zf, text="Zoom:").pack(side="right", padx=(8, 2))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        self.main_paned = tk.PanedWindow(self.tabs, orient="horizontal", sashwidth=6, sashrelief="flat",
                                    opaqueresize=False)

        # 1. Palette (left)
        left = tk.Frame(self.main_paned)
        self.catf = tk.Frame(left)
        self.catf.pack(fill="x")
        self.cat_labels = {}
        self.build_cats()
        sf = tk.Frame(left)
        sf.pack(fill="x", pady=2)
        tk.Label(sf, text="Search:").pack(side="left", padx=4)
        self.search_var = tk.StringVar()
        ttk.Entry(sf, textvariable=self.search_var).pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.search_var.trace_add("write", lambda *a: self.show_palette(self.cat))
        
        pf = tk.Frame(left)
        pf.pack(fill="both", expand=True)
        psb = ttk.Scrollbar(pf, orient="vertical")
        self.pal = tk.Canvas(pf, bg="#262932", highlightthickness=0, yscrollincrement=20, xscrollincrement=20)
        psb.configure(command=self.pal.yview)
        self.pal.configure(yscrollcommand=psb.set)
        psb.pack(side="right", fill="y")
        self.pal.pack(side="left", fill="both", expand=True)
        self.main_paned.add(left, minsize=260)

        # 2. Script area (center)
        mid = tk.Frame(self.main_paned)
        self.ws = tk.Canvas(mid, bg="#1b1d23", highlightthickness=0, yscrollincrement=20, xscrollincrement=20)
        vs = ttk.Scrollbar(mid, orient="vertical", command=self.ws.yview)
        hs = ttk.Scrollbar(mid, orient="horizontal", command=self.ws.xview)
        self.ws.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.ws.pack(side="left", fill="both", expand=True)
        self.main_paned.add(mid, minsize=300, stretch="always")

        # 3. Right panel (code + console + AI assistant)
        self.right_paned = tk.PanedWindow(self.main_paned, orient="vertical", sashwidth=6, sashrelief="flat",
                                     opaqueresize=False)
        
        # Python code.
        codef = tk.Frame(self.right_paned)
        head = tk.Frame(codef)
        head.pack(fill="x")
        tk.Label(head, text="Python code (editable)", font=self.font).pack(side="left", padx=4)
        ttk.Button(head, text="Copy", command=self.copy_code).pack(side="right", padx=4, pady=2)
        mono = tkfont.nametofont("TkFixedFont")
        self.code_status = tk.Label(codef, text="", anchor="w", justify="left", wraplength=400, font=self.efont)
        self.code_status.pack(side="bottom", fill="x", padx=6)
        cvs = ttk.Scrollbar(codef, orient="vertical")
        self.code = tk.Text(codef, bg=self.EDIT, fg="#e6e6e6", font=mono, wrap="none",
                            bd=0, padx=8, pady=6, undo=True, maxundo=-1,
                            insertbackground="#ffffff", selectbackground="#3b4261", inactiveselectbackground="#33384d",
                            yscrollcommand=cvs.set)
        cvs.configure(command=self.code.yview)
        cvs.pack(side="right", fill="y")
        self.code.pack(fill="both", expand=True)
        self.code.tag_configure("errline", background="#5a1d1d")
        self.code.bind("<<Modified>>", self.on_code_modified)
        self.code.bind("<Tab>", self.code_tab)
        self.code.bind("<Return>", self.code_return)
        for seq in ("<Shift-Tab>", "<ISO_Left_Tab>"):
            try:
                self.code.bind(seq, self.code_dedent)
            except tk.TclError:
                pass
        self.right_paned.add(codef, minsize=200)

        # Console
        conf = tk.Frame(self.right_paned)
        tk.Label(conf, text="Console", font=self.font).pack(anchor="w", padx=4)
        self.console = tk.Text(conf, bg="#101216", fg="#d6dae0", font=mono,
                               state="disabled", bd=0, padx=8, pady=4, wrap="word")
        self.console.tag_configure("err", foreground="#ff8a80")
        inp = tk.Frame(conf)
        inp.pack(side="bottom", fill="x", pady=2)      # Pack first so it stays visible.
        self.console.pack(fill="both", expand=True)
        tk.Label(inp, text="Input:").pack(side="left", padx=4)
        self.in_var = tk.StringVar()
        ent = ttk.Entry(inp, textvariable=self.in_var)
        ent.pack(side="left", fill="x", expand=True, pady=2)
        ent.bind("<Return>", self.send_input)
        ttk.Button(inp, text="Send", command=self.send_input).pack(side="left", padx=4)
        self.right_paned.add(conf, minsize=110)

        # Gemini AI assistant.
        ai_frame = tk.Frame(self.right_paned)
        ai_top = tk.Frame(ai_frame)
        ai_top.pack(fill="x")
        tk.Label(ai_top, text="Gemini AI assistant", font=self.font).pack(side="left", padx=4)
        ttk.Button(ai_top, text="New chat", command=self.ai_reset).pack(side="right", padx=2)
        ai_mod = tk.Frame(ai_frame)
        ai_mod.pack(fill="x", pady=2)
        tk.Label(ai_mod, text="Model:").pack(side="left", padx=4)
        saved_model = self.cfg.get("model")
        if saved_model not in DEFAULT_MODELS:
            saved_model = DEFAULT_MODELS[0]
        self.ai_model = tk.StringVar(value=saved_model)
        self.ai_combo = ttk.Combobox(
            ai_mod, textvariable=self.ai_model, values=DEFAULT_MODELS, state="readonly")
        self.ai_combo.pack(side="left", fill="x", expand=True, padx=2)
        ai_inp = tk.Frame(ai_frame)
        ai_inp.pack(side="bottom", fill="x", pady=4)
        tk.Label(ai_inp, text="Prompt:").pack(side="left", padx=4)
        self.ai_var = tk.StringVar()
        ai_ent = ttk.Entry(ai_inp, textvariable=self.ai_var)
        ai_ent.pack(side="left", fill="x", expand=True, padx=2)
        ai_ent.bind("<Return>", self.ask_gemini)
        self.ai_btn = ttk.Button(ai_inp, text="Ask", command=self.ask_gemini)
        self.ai_btn.pack(side="left", padx=4)
        ai_sb = ttk.Scrollbar(ai_frame, orient="vertical")
        ai_sb.pack(side="right", fill="y")
        self.ai_chat = tk.Text(ai_frame, bg=self.EDIT, fg="#d6dae0", font=mono, state="disabled",
                               bd=0, padx=8, pady=4, wrap="word", yscrollcommand=ai_sb.set)
        ai_sb.configure(command=self.ai_chat.yview)
        self.ai_chat.tag_configure("user", foreground="#a6e3a1")
        self.ai_chat.tag_configure("bot", foreground="#89b4fa")
        self.ai_chat.tag_configure("err", foreground="#f38ba8")
        self.ai_chat.tag_configure("info", foreground="#9399b2")
        self.ai_chat.tag_configure("who", foreground="#f9e2af", font=self.font)
        self.ai_chat.tag_configure("bold", font=self.font)
        self.ai_chat.tag_configure("icode", background="#313244", foreground="#f5e0dc")
        self.ai_chat.tag_configure("code", background="#11111b", foreground="#f5e0dc",
                                   lmargin1=10, lmargin2=10)
        self.ai_chat.tag_configure("undo", foreground="#f9e2af", underline=True)
        self.ai_chat.tag_bind("undo", "<Button-1>", self.ai_undo_apply)
        self.ai_chat.pack(fill="both", expand=True)

        self.ai_welcome()
        self.right_paned.add(ai_frame, minsize=200)

        self.main_paned.add(self.right_paned, minsize=300)

        self.tabs.add(self.main_paned, text="Workspace")
        self.settings_tab = ttk.Frame(self.tabs, padding=20)
        self.tabs.add(self.settings_tab, text="Settings")
        ttk.Label(self.settings_tab, text="Settings", font=self.font).pack(anchor="w", pady=(0, 16))
        appearance = ttk.LabelFrame(self.settings_tab, text="Appearance", padding=14)
        appearance.pack(anchor="nw", fill="x")
        ttk.Label(appearance, text="Theme").grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.settings_theme_var = tk.StringVar(value=self.theme_name)
        ttk.Radiobutton(appearance, text="Light", value="light",
                        variable=self.settings_theme_var,
                        command=lambda: self.set_theme(self.settings_theme_var.get())).grid(
                            row=0, column=1, sticky="w", padx=6)
        ttk.Radiobutton(appearance, text="Dark", value="dark",
                        variable=self.settings_theme_var,
                        command=lambda: self.set_theme(self.settings_theme_var.get())).grid(
                            row=0, column=2, sticky="w", padx=6)
        autosave_box = ttk.LabelFrame(self.settings_tab, text="Automatic save", padding=14)
        autosave_box.pack(anchor="nw", fill="x", pady=(0, 12))
        ttk.Label(autosave_box, text="Backup file").grid(row=0, column=0, sticky="w", padx=(0, 18))
        ttk.Label(autosave_box, text=os.path.join("save", "autosave.json")).grid(
            row=0, column=1, sticky="w")
        self.autosave_status_var = tk.StringVar(value="Waiting for changes")
        ttk.Label(autosave_box, textvariable=self.autosave_status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.palr = Renderer(self.pal, self.font)
        self.wsr = Renderer(self.ws, self.font, self.place_entry)

        for cv, src in ((self.pal, "pal"), (self.ws, "ws")):
            cv.bind("<ButtonPress-1>", lambda e, s=src: self.on_press(e, s))
            cv.bind("<B1-Motion>", self.on_motion)
            cv.bind("<ButtonRelease-1>", self.on_release)
        for seq in ("<ButtonPress-3>", "<ButtonPress-2>"):
            self.ws.bind(seq, self.on_context)
        mods = ["Control"] + (["Command"] if sys.platform == "darwin" else [])
        self.ws.bind("<Delete>", self.delete_selected)
        self.ws.bind("<BackSpace>", self.delete_selected)
        self.ws.bind("<Escape>", lambda e: (self.clear_selection(), "break")[1])
        for m in mods:
            for key, fn in (("a", self.select_all), ("d", self.duplicate_selected),
                            ("c", self.copy_selected), ("v", self.paste_clip)):
                for k in (key, key.upper()):
                    self.ws.bind("<%s-%s>" % (m, k), fn)
        root.bind_all("<Control-MouseWheel>", self.on_zoom_wheel)
        root.bind_all("<Control-Button-4>", self.on_zoom_wheel)
        root.bind_all("<Control-Button-5>", self.on_zoom_wheel)
        for seq, f in (("<Control-minus>", 0.8), ("<Control-plus>", 1.25), ("<Control-equal>", 1.25)):
            root.bind_all(seq, lambda e, f=f: self.zoom_by(f))
        root.bind_all("<Control-Key-0>", lambda e: self.set_zoom(1.0))
        for seq in ("<Control-o>", "<Control-O>"):
            root.bind_all(seq, lambda e: (self.open_file(), "break")[1])
        self.ws.bind("<Configure>", lambda e: self.draw_welcome(), add="+")
        root.bind_all("<MouseWheel>", self.on_wheel)
        root.bind_all("<Button-4>", self.on_wheel)
        root.bind_all("<Button-5>", self.on_wheel)
        self.apply_theme()

    def canvas_under(self, e):
        w = self.root.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if w is self.pal or w is self.ws:
                return w
            w = getattr(w, "master", None)
        return None

    def on_wheel(self, e):
        target = self.canvas_under(e)
        if target is None:
            return
        up = e.num == 4 or getattr(e, "delta", 0) > 0
        target.yview_scroll(-3 if up else 3, "units")

    def on_zoom_wheel(self, e):
        if self.canvas_under(e) is not self.ws:
            return "break"
        up = e.num == 4 or getattr(e, "delta", 0) > 0
        self.set_zoom(self.zoom * (1.1 if up else 1 / 1.1),
                      e.x_root - self.ws.winfo_rootx(), e.y_root - self.ws.winfo_rooty())
        return "break"

    def zoom_by(self, f):
        self.set_zoom(self.zoom * f)

    def set_zoom(self, z, ax=None, ay=None):
        z = max(0.25, min(2.0, z))
        if abs(z - self.zoom) < 1e-6:
            return
        c = self.ws
        if ax is None:
            ax, ay = c.winfo_width() / 2, c.winfo_height() / 2
        lx, ly = c.canvasx(ax) / self.zoom, c.canvasy(ay) / self.zoom
        self.zoom = z
        self.zoom_var.set("%d %%" % round(z * 100))
        self.render()
        sr = [float(v) for v in str(c.cget("scrollregion")).split()]
        W, H = max(sr[2] - sr[0], 1), max(sr[3] - sr[1], 1)
        c.xview_moveto(max(0.0, lx * z - ax) / W)
        c.yview_moveto(max(0.0, ly * z - ay) / H)

    # ---------- palette ----------
    def build_cats(self):
        for w in self.catf.winfo_children():
            w.destroy()
        self.cat_labels = {}
        for i, (name, (col, _)) in enumerate(CATS.items()):
            lb = tk.Label(self.catf, text=name, bg=col, fg=text_on(col), font=self.font,
                          padx=8, pady=5, cursor="hand2", bd=2, relief="flat")
            lb.grid(row=i // 3, column=i % 3, sticky="nsew", padx=1, pady=1)
            lb.bind("<Button-1>", lambda e, n=name: self.show_palette(n))
            self.cat_labels[name] = lb
        for c in range(3):
            self.catf.grid_columnconfigure(c, weight=1, uniform="category-columns")
        for r in range((len(CATS) + 2) // 3):
            self.catf.grid_rowconfigure(r, weight=1, uniform="category-rows")

    def palette_types(self, cat):
        q = self.search_var.get().strip().lower()
        if not q:
            return ORDER[cat]
        return [t for c in ORDER for t in ORDER[c]
                if q in SPECS[t]["label"].lower() or q in t.lower()]

    def pip_install(self, pkg):
        self.root.configure(cursor="watch")
        self.root.update()
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                               capture_output=True, text=True)
        except Exception as ex:
            return False, str(ex)
        finally:
            self.root.configure(cursor="")
        importlib.invalidate_caches()
        return r.returncode == 0, (r.stdout + r.stderr)[-700:]

    def try_import(self, name):
        try:
            import_library(name)
            return True
        except ModuleNotFoundError:
            if getattr(sys, "frozen", False):
                messagebox.showerror(
                    "Import", "'%s' is not included in this .exe application.\n"
                    "Use scratchpy.py with Python, or rebuild the .exe with "
                    "--hidden-import %s." % (name, name.split(".")[0]))
                return False
            pkg = simpledialog.askstring(
                "Library not found",
                "'%s' is not installed.\nEnter the package name to install with pip "
                "(leave blank to cancel):" % name,
                initialvalue=name.split(".")[0], parent=self.root)
            if not pkg or not pkg.strip():
                return False
            ok, log = self.pip_install(pkg.strip())
            if not ok:
                messagebox.showerror("pip", "Installation failed:\n%s" % log)
                return False
            try:
                import_library(name)
                return True
            except Exception as ex:
                messagebox.showerror("Import", "Could not import '%s':\n%s" % (name, ex))
                return False
        except Exception as ex:
            messagebox.showerror("Import", "Could not import '%s':\n%s" % (name, ex))
            return False

    def import_lib(self, name=None):
        if name is None:
            name = simpledialog.askstring(
                "Import a library",
                "Python module name (e.g. math, random, string, os.path, turtle, numpy):",
                parent=self.root)
        if not name or not name.strip():
            return
        name = name.strip()
        if not self.try_import(name):
            return
        if name not in self.libs:
            self.libs.append(name)
        if "import %s" % name not in self.import_lines:
            self.import_lines.append("import %s" % name)
        self.search_var.set("")
        self.build_cats()
        self.show_palette(name)
        self.refresh()

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[("Python module", "*.py")])
        if not path:
            return
        d, base = os.path.split(path)
        if d not in sys.path:
            sys.path.insert(0, d)
        if d not in self.paths:
            self.paths.append(d)
        self.import_lib(os.path.splitext(base)[0])

    def show_palette(self, cat):
        self.cat = cat
        for n, lb in self.cat_labels.items():
            lb.configure(relief="sunken" if n == cat else "flat")
        self.pal.delete("all")
        r = self.palr
        r.reset()
        y = 14
        for t in self.palette_types(cat):
            b = Block(t)
            r.force_ctx = ("palette", t)
            if b.shape in REPORTERS:
                r.draw_reporter(b, 16, y, None)
                h = r.rsize(b)[1]
            else:
                r.draw_stmt(b, 16, y, [b], 0)
                h = r.ssize(b)[1]
            y += h + 16
        r.force_ctx = None
        bb = self.pal.bbox("shape")
        self.pal.configure(scrollregion=(0, 0, max(320, (bb[2] if bb else 0) + 20), y + 10))
        self.pal.yview_moveto(0)
        self.pal.xview_moveto(0)

    # ---------- script area ----------
    def place_entry(self, b, idx, x, y, w, h):
        key = (b.uid, idx)
        self.used.add(key)
        got = self.entries.get(key)
        if got is None:
            var = tk.StringVar(value=b.fields[idx])
            ent = tk.Entry(self.ws, textvariable=var, bg="white", fg="#575E75", bd=0,
                           highlightthickness=1, highlightbackground="#d0d0d0",
                           highlightcolor="#4C97FF", justify="center", font=self.efont,
                           insertbackground="#575E75", relief="flat")
            var.trace_add("write", lambda *a, b=b, idx=idx, var=var: self.field_changed(b, idx, var))
            item = self.ws.create_window(x, y, window=ent, anchor="nw", width=w, height=h)
            self.entries[key] = (ent, item)
        else:
            ent, item = got
            self.ws.coords(item, x, y)
            self.ws.itemconfigure(item, width=w, height=h)

    def field_changed(self, b, idx, var):
        if isinstance(b.fields[idx], str):
            b.fields[idx] = var.get()
            if self._job is None:
                self._job = self.root.after_idle(self.refresh)

    def refresh(self):
        self._job = None
        self.render()
        self.update_code()

    def draw_script(self, r, s):
        if s.blocks[0].shape in REPORTERS:
            r.draw_reporter(s.blocks[0], s.x, s.y, ("script", s))
        else:
            r.draw_list(s.blocks, s.x, s.y)

    def draw_welcome(self):
        """Show the welcome screen while the workspace is empty."""
        c = self.ws
        c.delete("welcome")
        if self.scripts or self.drag:
            return
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        cx, cy = c.canvasx(w / 2), c.canvasy(h / 2)
        c.create_text(cx, cy - 30, text="Start your program", fill=self.FG,
                      font=(self.font.actual("family"), 20, "bold"), tags="welcome")
        c.create_text(cx, cy + 12, text="Drag a block from the palette to get started", fill=self.MUTED,
                      font=(self.font.actual("family"), 13), tags="welcome")
        c.create_text(cx, cy + 40, text="or press Ctrl + O to open a file",
                  fill=self.MUTED, font=(self.font.actual("family"), 13), tags="welcome")
        c.tag_lower("welcome")

    def render(self, preview=False):
        c, r, z = self.ws, self.wsr, self.zoom
        c.delete("shape")
        r.reset()
        self.used = set()
        r.selected = self.sel
        for s in self.scripts:
            self.draw_script(r, s)
        d = self.drag
        if d:
            r.in_drag = True
            if "group" in d:
                for g in d["group"]:
                    self.draw_script(r, Script(d["x"] + g["dx"], d["y"] + g["dy"], g["blocks"]))
            else:
                self.draw_script(r, Script(d["x"], d["y"], d["blocks"]))
            r.in_drag = False
            if preview and "group" not in d:
                self.show_preview(self.find_target(d))
        for key in list(self.entries):
            if key not in self.used:
                ent, item = self.entries.pop(key)
                c.delete(item)
                ent.destroy()
        # Draw everything at scale 1, then scale the canvas items.
        if z != 1.0:
            c.scale("shape", 0, 0, z, z)
        size = max(3, round(10 * z))
        self.zfont.configure(size=size)
        self.zefont.configure(size=size)
        c.itemconfigure("txt", font=self.zfont)
        for key in self.used:
            ent, item = self.entries[key]
            x, y = c.coords(item)
            c.coords(item, x * z, y * z)
            c.itemconfigure(item, width=float(c.itemcget(item, "width")) * z,
                            height=float(c.itemcget(item, "height")) * z)
            ent.configure(font=self.zefont)
        bb = c.bbox("shape")
        w = max(c.winfo_width(), (bb[2] if bb else 0) + 250)
        h = max(c.winfo_height(), (bb[3] if bb else 0) + 250)
        c.configure(scrollregion=(0, 0, w, h))
        self.draw_welcome()

    # ---------- editable code (code and blocks stay in sync) ----------
    def current_code(self):
        return self.code.get("1.0", "end-1c")

    def set_code_status(self, err=None):
        self.code.tag_remove("errline", "1.0", "end")
        self.code_error = err
        if err is None:
            self.code_status.configure(text="✓ Code and blocks are synchronized", fg="#7ee2a0")
            return
        n = getattr(err, "lineno", None)
        msg = getattr(err, "msg", None) or str(err)
        self.code_status.configure(
              text="⚠ Error%s: %s\nBlocks will update when the code is valid."
                  % ((" on line %d" % n) if n else "", msg), fg="#ff8a80")
        if n:
            self.code.tag_add("errline", "%d.0" % n, "%d.end" % n)

    def update_code(self):
        """Blocks -> code. Never overwrite code while the user is fixing a syntax error."""
        if self.code_error is not None:
            return
        if self._code_job:
            self.root.after_cancel(self._code_job)
            self._code_job = None
        text = generate(self.scripts, self.libs, self.paths, self.import_lines)
        if text == self.current_code():
            return
        top = self.code.yview()[0]
        self.code.delete("1.0", "end")
        self.code.insert("1.0", text)
        self.code.yview_moveto(top)
        self.code.edit_reset()
        self.code.edit_modified(False)
        self.set_code_status(None)

    def on_code_modified(self, e=None):
        if not self.code.edit_modified():       # This change came from the program; ignore it.
            return
        self.code.edit_modified(False)
        if self._code_job:
            self.root.after_cancel(self._code_job)
        self._code_job = self.root.after(700, self.apply_code)

    def sync_libs(self, imports):
        """Keep palette libraries in sync with imports in the code."""
        mods = []
        for mod, line in imports:
            if mod != "__future__" and mod not in mods:
                mods.append(mod)
        changed = False
        for m in list(self.libs):
            if m not in mods:
                unload_library(m)
                self.libs.remove(m)
                changed = True
        for m in mods:
            if m in self.libs:
                continue
            try:                                # Do not open a pip dialog while typing; ignore missing modules.
                if importlib.util.find_spec(m.split(".")[0]) is None:
                    continue
                import_library(m)
            except Exception:
                continue
            self.libs.append(m)
            changed = True
        return changed

    def apply_code(self):
        """Convert code to blocks shortly after the last keystroke."""
        self._code_job = None
        src = self.current_code()
        try:
            tree = ast.parse(src)
        except Exception as ex:                 # SyntaxError, including IndentationError and TabError.
            self.set_code_status(ex)
            return
        self.set_code_status(None)
        try:                                    # Preserve blocks when only whitespace or comments changed.
            if ast.dump(tree) == ast.dump(ast.parse(
                    generate(self.scripts, self.libs, self.paths, self.import_lines))):
                return
        except Exception:
            pass
        try:
            blocks, imports, paths = python_to_project(src, generated=True)
        except Exception as ex:
            self.set_code_status(ex)
            return
        self.stop_drag()
        self.scripts = [Script(30, 30, [Block("start")] + blocks)]
        self.sel = set()
        self.import_lines = [line for mod, line in imports]
        self.paths = paths
        for d in paths:
            if d not in sys.path:
                sys.path.insert(0, d)
        if self.sync_libs(imports):
            self.build_cats()
            self.show_palette(self.cat if self.cat in CATS else "Control")
        self.render()

    def stop_drag(self):
        self.drag = None
        self.band = None

    def _replace_selection(self):
        if self.code.tag_ranges("sel"):
            self.code.delete("sel.first", "sel.last")

    def code_tab(self, e):
        self._replace_selection()
        self.code.insert("insert", "    ")
        return "break"

    def code_dedent(self, e):
        line = self.code.get("insert linestart", "insert lineend")
        n = min(4, len(line) - len(line.lstrip(" ")))
        if n:
            self.code.delete("insert linestart", "insert linestart+%dc" % n)
        return "break"

    def code_return(self, e):
        self._replace_selection()
        before = self.code.get("insert linestart", "insert")
        indent = before[:len(before) - len(before.lstrip(" "))]
        if before.rstrip().endswith(":"):
            indent += "    "
        self.code.insert("insert", "\n" + indent)
        self.code.see("insert")
        return "break"

    def pointer_ws(self, e):
        return (self.ws.canvasx(e.x_root - self.ws.winfo_rootx()) / self.zoom,
                self.ws.canvasy(e.y_root - self.ws.winfo_rooty()) / self.zoom)

    def is_inside(self, e):
        x, y = e.x_root - self.ws.winfo_rootx(), e.y_root - self.ws.winfo_rooty()
        return 0 <= x < self.ws.winfo_width() and 0 <= y < self.ws.winfo_height()

    # ---------- multi-selection ----------
    ADD_MASK = 0x5 | (0x8 if sys.platform == "darwin" else 0)     # Shift, Ctrl (and Cmd on Mac).

    def iter_blocks(self):
        """Yield every block as (block, context, parent_is_selected)."""
        sel = self.sel

        def lst(L, anc):
            for i, b in enumerate(L):
                yield b, ("list", L, i), anc
                yield from inner(b, anc or b.uid in sel)

        def inner(b, anc):
            for idx, f in enumerate(b.fields):
                if isinstance(f, Block):
                    yield f, ("slot", b, idx), anc
                    yield from inner(f, anc or f.uid in sel)
            yield from lst(b.body, anc)
            yield from lst(b.orelse, anc)

        for s in self.scripts:
            b0 = s.blocks[0]
            if b0.shape in REPORTERS:
                yield b0, ("script", s), False
                yield from inner(b0, b0.uid in sel)
            else:
                yield from lst(s.blocks, False)

    def sel_roots(self):
        """Return selected blocks without a selected parent; children move with their parent."""
        return [(b, ctx) for b, ctx, anc in self.iter_blocks() if b.uid in self.sel and not anc]

    def selection_groups(self):
        """Group selected blocks into stacks, keeping adjacent blocks together."""
        pos = {}
        for h in self.wsr.hits:
            pos.setdefault(h[4].uid, (h[0], h[1]))
        groups = []
        for b, ctx in self.sel_roots():
            x, y = pos.get(b.uid, (0, 0))
            g = groups[-1] if groups else None
            if g and ctx[0] == "list" and g["L"] is ctx[1] and ctx[2] == g["i"] + 1:
                g["blocks"].append(b)
                g["i"] = ctx[2]
            else:
                islist = ctx[0] == "list"
                groups.append({"blocks": [b], "x": x, "y": y,
                               "L": ctx[1] if islist else None, "i": ctx[2] if islist else -2})
        return groups

    def detach(self, b, ctx):
        if ctx[0] == "list":
            L = ctx[1]
            for k, x in enumerate(L):
                if x is b:
                    del L[k]
                    break
        elif ctx[0] == "slot":
            if ctx[1].fields[ctx[2]] is b:
                ctx[1].fields[ctx[2]] = ""
        elif ctx[1] in self.scripts:
            self.scripts.remove(ctx[1])

    def toggle_select(self, b):
        if b.uid in self.sel:
            self.sel.discard(b.uid)
        else:
            self.sel.add(b.uid)
        self.render()

    def clear_selection(self):
        if self.sel:
            self.sel = set()
            self.render()

    def select_all(self, ev=None):
        self.sel = {b.uid for b, ctx, anc in self.iter_blocks()}
        self.render()
        return "break"

    def delete_selected(self, ev=None):
        roots = self.sel_roots()
        for b, ctx in roots:
            self.detach(b, ctx)
        self.sel = set()
        self.scripts = [s for s in self.scripts if s.blocks]
        if roots:
            self.refresh()
        return "break"

    def duplicate_selected(self, ev=None):
        groups = self.selection_groups()
        if not groups:
            return "break"
        new = set()
        for g in groups:
            clones = [from_dict(to_dict(b)) for b in g["blocks"]]
            self.scripts.append(Script(g["x"] + 30, g["y"] + 30, clones))
            new.update(c.uid for c in clones)
        self.sel = new
        self.refresh()
        return "break"

    def copy_selected(self, ev=None):
        groups = self.selection_groups()
        if groups:
            self.clip = [([to_dict(b) for b in g["blocks"]], g["x"], g["y"]) for g in groups]
            self.paste_n = 0
        return "break"

    def paste_clip(self, ev=None):
        if not self.clip:
            return "break"
        self.paste_n += 1
        k = 30 * self.paste_n
        try:
            new, added = set(), []
            for blocks, x, y in self.clip:
                clones = [from_dict(d) for d in blocks]
                added.append(Script(x + k, y + k, clones))
                new.update(c.uid for c in clones)
        except ValueError:                 # A block belongs to a library that is no longer imported.
            self.clip = []
            return "break"
        self.scripts.extend(added)
        self.sel = new
        self.refresh()
        return "break"

    # Mouse-drag selection rectangle.
    def start_band(self, cx, cy, add):
        had = bool(self.sel)
        base = set(self.sel) if add else set()
        self.band = {"x0": cx, "y0": cy, "base": base}
        if not add:
            self.sel = set()
            if had:
                self.render()

    def band_motion(self, e):
        bd = self.band
        x1, y1 = self.pointer_ws(e)
        xa, xb = sorted((bd["x0"], x1))
        ya, yb = sorted((bd["y0"], y1))
        touched = {h[4].uid for h in self.wsr.hits
                   if h[0] <= xb and h[0] + h[2] >= xa and h[1] <= yb and h[1] + h[3] >= ya}
        new = bd["base"] | touched
        if new != self.sel:
            self.sel = new
            self.render()
        z = self.zoom
        self.ws.delete("band")
        self.ws.create_rectangle(bd["x0"] * z, bd["y0"] * z, x1 * z, y1 * z, outline="#2563EB",
                                 width=2, dash=(4, 3), tags="band")

    def band_release(self):
        self.ws.delete("band")
        self.band = None

    def start_group_drag(self, cx, cy):
        groups = self.selection_groups()
        if not groups:
            return
        gx, gy = groups[0]["x"], groups[0]["y"]
        for g in groups:
            g["dx"], g["dy"] = g["x"] - gx, g["y"] - gy
        for b, ctx in self.sel_roots():
            self.detach(b, ctx)
        self.scripts = [s for s in self.scripts if s.blocks]
        self.drag = {"blocks": groups[0]["blocks"], "off": (cx - gx, cy - gy), "x": gx, "y": gy}
        if len(groups) > 1:
            self.drag["group"] = groups

    # ---------- drag and drop ----------
    def on_press(self, e, src):
        cv = self.pal if src == "pal" else self.ws
        cv.focus_set()
        r = self.palr if src == "pal" else self.wsr
        zz = self.zoom if src == "ws" else 1.0
        cx, cy = cv.canvasx(e.x) / zz, cv.canvasy(e.y) / zz
        hit = r.find(cx, cy)
        add = src == "ws" and bool(getattr(e, "state", 0) & self.ADD_MASK)
        if not hit:
            if src == "ws":
                self.start_band(cx, cy, add)
            return
        x, y, w, h, b, ctx = hit
        if add:                                     # Ctrl / Shift + click toggles selection.
            self.toggle_select(b)
            return
        if src == "ws" and b.uid in self.sel and len(self.sel_roots()) > 1:
            self.start_group_drag(cx, cy)           # Move the full selection.
            self.on_motion(e)
            return
        self.sel = set()
        if ctx[0] == "palette":
            blocks = [Block(ctx[1])]
        elif ctx[0] == "list":
            L, i = ctx[1], ctx[2]
            blocks = L[i:]
            del L[i:]
        elif ctx[0] == "slot":
            parent, idx = ctx[1], ctx[2]
            blocks = [parent.fields[idx]]
            parent.fields[idx] = ""
        else:
            blocks = [b]
            self.scripts.remove(ctx[1])
        self.scripts = [s for s in self.scripts if s.blocks]
        self.drag = {"blocks": blocks, "off": (cx - x, cy - y), "x": x, "y": y}
        self.on_motion(e)

    def on_motion(self, e):
        if self.band:
            self.band_motion(e)
            return
        d = self.drag
        if not d:
            return
        px, py = self.pointer_ws(e)
        d["x"], d["y"] = px - d["off"][0], py - d["off"][1]
        self.inside = self.is_inside(e)
        # Redraw at most once per frame (~60 times per second), merging intervening mouse events
        # instead of triggering a full redraw for each one.
        if self._drag_job is None:
            self._drag_job = self.root.after(15, self._drag_frame)

    def _drag_frame(self):
        self._drag_job = None
        if self.drag:
            self.render(preview=self.inside)

    def find_target(self, d):
        r = self.wsr
        blocks, dx, dy = d["blocks"], d["x"], d["y"]
        first = blocks[0]
        if len(blocks) == 1 and first.shape in REPORTERS:
            w, h = r.rsize(first)
            px, py = dx + 10, dy + h / 2
            best = None
            for sx, sy, sw, sh, parent, idx, indrag in r.slots:
                if indrag:
                    continue
                if sx - 6 <= px <= sx + sw + 6 and sy - 6 <= py <= sy + sh + 6:
                    outside = not (sx <= px <= sx + sw and sy <= py <= sy + sh)
                    distance = math.hypot(px - (sx + sw / 2), py - (sy + sh / 2))
                    rank = (outside, sw * sh, distance)
                    if best is None or rank < best[0]:
                        best = (rank, ("slot", parent, idx, sx, sy, sw, sh))
            return best[1] if best else None
        H = r.lsize(blocks)
        hat = first.shape == "hat"
        best, bd = None, 36
        for sx, sy, L, i, indrag in r.snaps:
            if indrag:
                continue
            if i == 0 and L and L[0].shape == "hat":
                continue
            top_level = any(L is s.blocks for s in self.scripts)
            if hat:
                if not (top_level and i == 0):
                    continue
                cands = [math.hypot(dx - sx, dy + H - sy)]
            else:
                cands = [math.hypot(dx - sx, dy - sy)]
                if i < len(L):
                    cands.append(math.hypot(dx - sx, dy + H - sy))
            dd = min(cands)
            if dd < bd:
                bd, best = dd, ("stack", L, i, sx, sy)
        return best

    def show_preview(self, tgt):
        if not tgt:
            return
        if tgt[0] == "stack":
            _, L, i, sx, sy = tgt
            self.ws.create_line(sx, sy, sx + 100, sy, fill="#4C97FF", width=5, tags="shape")
        else:
            _, parent, idx, sx, sy, sw, sh = tgt
            self.ws.create_rectangle(sx - 2, sy - 2, sx + sw + 2, sy + sh + 2,
                                     outline="#4C97FF", width=3, tags="shape")

    def block_size(self, blocks):
        r = self.wsr
        if blocks and blocks[0].shape in REPORTERS:
            return r.rsize(blocks[0])
        return max((r.hsize(b)[0] for b in blocks), default=0), r.lsize(blocks)

    def free_position(self, x, y, w, h):
        gap = 12
        while True:
            next_y = y
            for script in self.scripts:
                sw, sh = self.block_size(script.blocks)
                if (x < script.x + sw + gap and x + w + gap > script.x and
                        y < script.y + sh + gap and y + h + gap > script.y):
                    next_y = max(next_y, script.y + sh + gap)
            if next_y == y:
                return x, y
            y = next_y

    def on_release(self, e):
        if self.band:
            self.band_release()
            return
        d = self.drag
        if not d:
            return
        if self._drag_job is not None:
            self.root.after_cancel(self._drag_job)
            self._drag_job = None
        inside = self.is_inside(e)
        if "group" in d:                            # Multiple stacks are moved together.
            self.drag = None
            if inside:
                bounds = [(g["dx"], g["dy"], *self.block_size(g["blocks"]))
                          for g in d["group"]]
                left = min(g[0] for g in bounds)
                top = min(g[1] for g in bounds)
                right = max(g[0] + g[2] for g in bounds)
                bottom = max(g[1] + g[3] for g in bounds)
                x, y = self.free_position(max(d["x"] + left, 4), max(d["y"] + top, 4),
                                          right - left, bottom - top)
                shift_x = x - (d["x"] + left)
                shift_y = y - (d["y"] + top)
                for g in d["group"]:
                    self.scripts.append(Script(d["x"] + g["dx"] + shift_x,
                                               d["y"] + g["dy"] + shift_y, g["blocks"]))
            else:
                self.sel = set()
            self.scripts = [s for s in self.scripts if s.blocks]
            self.refresh()
            return
        tgt = self.find_target(d) if inside else None
        self.drag = None
        if inside:
            blocks = d["blocks"]
            if tgt and tgt[0] == "stack":
                _, L, i, _, _ = tgt
                L[i:i] = blocks
            elif tgt and tgt[0] == "slot":
                _, parent, idx, sx, sy, _, _ = tgt
                old = parent.fields[idx]
                parent.fields[idx] = blocks[0]
                if isinstance(old, Block):
                    x, y = self.free_position(sx + 30, sy + 30, *self.block_size([old]))
                    self.scripts.append(Script(x, y, [old]))
            else:
                x, y = max(d["x"], 4), max(d["y"], 4)
                x, y = self.free_position(x, y, *self.block_size(blocks))
                self.scripts.append(Script(x, y, blocks))
        self.scripts = [s for s in self.scripts if s.blocks]
        self.refresh()

    def on_context(self, e):
        cx, cy = self.ws.canvasx(e.x) / self.zoom, self.ws.canvasy(e.y) / self.zoom
        hit = self.wsr.find(cx, cy)
        if not hit:
            return "break"
        x, y, w, h, b, ctx = hit
        menu = tk.Menu(self.root, tearoff=0)
        roots = self.sel_roots()
        if b.uid in self.sel and len(roots) > 1:
            menu.add_command(label="Duplicate selection (%d blocks)" % len(roots),
                             command=self.duplicate_selected)
            menu.add_command(label="Delete selection", command=self.delete_selected)
            menu.add_command(label="Deselect all", command=self.clear_selection)
            menu.tk_popup(e.x_root, e.y_root)
            return "break"

        def dup():
            if ctx[0] == "list":
                clones = [from_dict(to_dict(k)) for k in ctx[1][ctx[2]:]]
            else:
                clones = [from_dict(to_dict(b))]
            self.scripts.append(Script(x + 30, y + 30, clones))
            self.refresh()

        def delete():
            if ctx[0] == "list":
                ctx[1].pop(ctx[2])
            elif ctx[0] == "slot":
                ctx[1].fields[ctx[2]] = ""
            else:
                self.scripts.remove(ctx[1])
            self.scripts = [s for s in self.scripts if s.blocks]
            self.refresh()

        menu.add_command(label="Duplicate", command=dup)
        menu.add_command(label="Delete this block", command=delete)
        menu.tk_popup(e.x_root, e.y_root)
        return "break"

    # ---------- project ----------
    def set_scripts(self, scripts):
        self.stop()
        self.scripts = scripts
        self.sel = set()
        self.code_error = None
        self.build_cats()
        self.show_palette(self.cat if self.cat in CATS else "Control")
        self.refresh()

    def project_state(self):
        data = {
            "scripts": [{"x": s.x, "y": s.y, "blocks": [to_dict(b) for b in s.blocks]}
                        for s in self.scripts],
            "paths": self.paths,
            "libs": self.libs,
            "imports": self.import_lines,
            "code": self.current_code(),
        }
        return json.dumps(data, sort_keys=True, ensure_ascii=False)

    def mark_saved(self):
        self.saved_state = self.project_state()

    def project_data(self):
        return {"version": 1, "paths": self.paths, "libs": self.libs,
                "imports": self.import_lines, "scripts": [
            {"x": s.x, "y": s.y, "blocks": [to_dict(b) for b in s.blocks]}
            for s in self.scripts], "code": self.current_code()}

    def write_autosave(self, force=False):
        state = self.project_state()
        if not force and state == self.autosaved_state:
            return False
        folder = os.path.dirname(self.autosave_path)
        temp_path = None
        try:
            os.makedirs(folder, exist_ok=True)
            fd, temp_path = tempfile.mkstemp(prefix=".autosave-", suffix=".tmp", dir=folder)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump(self.project_data(), output, ensure_ascii=False, indent=1)
            os.replace(temp_path, self.autosave_path)
            temp_path = None
        except OSError as ex:
            if hasattr(self, "autosave_status_var"):
                self.autosave_status_var.set("Auto-save failed: %s" % ex)
            return False
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        self.autosaved_state = state
        if hasattr(self, "autosave_status_var"):
            self.autosave_status_var.set("Project saved automatically")
        return True

    def autosave_tick(self):
        self.autosave_job = None
        if self.closing:
            return
        self.write_autosave()
        self.autosave_job = self.root.after(self.autosave_interval, self.autosave_tick)

    def restore_autosave(self):
        if not os.path.isfile(self.autosave_path):
            return
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py"):
            return
        if messagebox.askyesno(
                "Restore autosave?", "An automatically saved project was found. Restore it?",
                parent=self.root):
            self.open_file(self.autosave_path)
            self.autosaved_state = self.project_state()
        else:
            try:
                os.remove(self.autosave_path)
            except OSError:
                pass
            self.autosaved_state = self.project_state()

    def new(self):
        if (self.scripts or self.libs) and not messagebox.askyesno(
                "New project", "Clear the current project (blocks and imported libraries)?"):
            return
        for d in self.paths:
            if d in sys.path:
                sys.path.remove(d)
        unload_libraries()
        self.libs, self.paths, self.import_lines = [], [], []
        self.clip = []
        self.cat = "Control"
        self.search_var.set("")
        self.set_scripts([])
        self.mark_saved()

    def load_example(self):
        B = Block
        main = Script(30, 30, [
            B("start"),
            B("set", ["total", "0"]),
            B("for", ["i", B("pyexpr", ["range(1, 6)"])], [
                B("change", ["total", B("var", ["i"])]),
                B("print", [B("join", ['"Partial sum: "', B("str", [B("var", ["total"])])])]),
            ]),
            B("if", [B("gt", [B("var", ["total"]), "10"])],
              [B("print", ['"It is greater than 10!"'])]),
            B("elif", [B("eq", [B("var", ["total"]), "10"])],
                            [B("print", ['"Exactly 10."'])]),
                        B("else", [], [B("print", ['"It is less than 10."'])]),
        ])
        fn = Script(420, 30, [
            B("def", ["greet", "name"], [
                B("print", [B("join", ['"Hello "', B("var", ["name"])])])]),
        ])
        call = Script(420, 190, [B("start"), B("call", ["greet", '"Scratch"'])])
        self.set_scripts([main, fn, call])

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                            filetypes=[("ScratchPy project", "*.json")])
        if not path:
            return False
        data = self.project_data()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except OSError as ex:
            messagebox.showerror("Save project", "Could not save the project:\n%s" % ex,
                                 parent=self.root)
            return False
        self.mark_saved()
        return True

    def open_py(self, path):
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                src = f.read()
            blocks, imports, _ = python_to_project(src)
        except SyntaxError as ex:
            messagebox.showerror("Open", "Syntax error in this Python file "
                                 "(line %s):\n%s" % (ex.lineno, ex.msg))
            return
        except Exception as ex:
            messagebox.showerror("Open", "Could not read the file:\n%s" % ex)
            return
        if count_blocks(blocks) > 2500 and not messagebox.askyesno(
                "Large file", "This file will create more than 2,500 blocks and may be slow. "
                "Continue?"):
            return
        d = os.path.dirname(os.path.abspath(path))
        local = set(local_imports(src, d))
        if local and d not in self.paths:
            self.paths.append(d)
        # Imports do not become blocks; they create library categories.
        self.import_lines = []
        new_libs = []
        for mod, line in imports:
            if line not in self.import_lines:
                self.import_lines.append(line)
            if mod == "__future__":
                continue
            if mod.split(".")[0] in local:
                if not messagebox.askyesno(
                        "Local module",
                        "This file imports '%s', a module located beside it.\n"
                        "Creating its blocks will execute it in the editor. Continue?" % mod):
                    continue
                if d not in sys.path:
                    sys.path.insert(0, d)
            if self.try_import(mod):
                if mod not in self.libs:
                    self.libs.append(mod)
                if mod not in new_libs:
                    new_libs.append(mod)
        self.set_scripts([Script(30, 30, [Block("start")] + blocks)])
        self.mark_saved()
        if new_libs:
            self.search_var.set("")
            self.show_palette(new_libs[0])

    def open_file(self, path=None):
        if not path:
            path = filedialog.askopenfilename(filetypes=[
                ("Python file or project", "*.py *.json"),
                ("Python file", "*.py"), ("ScratchPy project", "*.json")])
        if not path:
            return
        if path.lower().endswith(".py"):
            self.open_py(path)
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("paths", []):
                if d not in sys.path:
                    sys.path.insert(0, d)
                if d not in self.paths:
                    self.paths.append(d)
            self.import_lines = list(data.get("imports", []))
            for m in data.get("libs", []):
                import_library(m)
                if m not in self.libs:
                    self.libs.append(m)
            scripts = [Script(s["x"], s["y"], [from_dict(b) for b in s["blocks"]])
                       for s in data["scripts"]]
        except Exception as ex:
            messagebox.showerror("Open", "Invalid file:\n%s" % ex)
            return
        self.set_scripts(scripts)
        saved_code = data.get("code")
        if isinstance(saved_code, str):
            self.code.delete("1.0", "end")
            self.code.insert("1.0", saved_code)
            self.code.edit_modified(False)
            self.apply_code()
        self.mark_saved()
        self.autosaved_state = self.project_state()

    def export_py(self):
        path = filedialog.asksaveasfilename(defaultextension=".py",
                                            filetypes=[("Python", "*.py")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.current_code())

    def copy_code(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.current_code())

    # ---------- execution ----------
    MAX_LINES = 3000                     # Keep the last 3,000 console lines.

    def console_write(self, text, tag=None):
        lines = text.split("\n")
        if len(lines) > self.MAX_LINES:
            text = "\n".join(lines[-self.MAX_LINES:])
        c = self.console
        c.configure(state="normal")
        c.insert("end", text, tag)
        n = int(c.index("end-1c").split(".")[0])
        if n > self.MAX_LINES:
            c.delete("1.0", "%d.0" % (n - self.MAX_LINES))
        c.see("end")
        c.configure(state="disabled")

    def run(self):
        self.stop(quiet=True)
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")
        path = os.path.join(tempfile.gettempdir(), "scratchpy_program.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.current_code())
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        try:
            self.proc = subprocess.Popen(python_command(path), stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                         creationflags=(0x08000000 if sys.platform == "win32" else 0))
        except Exception as ex:
            self.console_write("Could not start Python: %s\n" % ex, "err")
            return
        self.token += 1
        threading.Thread(target=self.reader, args=(self.proc, self.token), daemon=True).start()

    def put_item(self, token, kind, val):
        """Queue output, slowing the program if the UI cannot keep up."""
        while True:
            try:
                self.q.put((token, kind, val), timeout=0.2)
                return True
            except queue.Full:
                if token != self.token:          # The program was stopped or restarted; discard output.
                    return False

    def reader(self, proc, token):
        fd = proc.stdout.fileno()
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        while True:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            if not self.put_item(token, "out", dec.decode(data)):
                return
        tail = dec.decode(b"", final=True)
        if tail and not self.put_item(token, "out", tail):
            return
        self.put_item(token, "end", proc.wait())

    def poll(self):
        """Display output in small batches to keep the window responsive."""
        t0 = time.monotonic()
        buf, size, end, busy = [], 0, None, False
        try:
            while True:
                if size >= 32768 or time.monotonic() - t0 > 0.02:
                    busy = True
                    break
                token, kind, val = self.q.get_nowait()
                if token != self.token:
                    continue
                if kind == "out":
                    buf.append(val)
                    size += len(val)
                else:
                    end = val
                    break
        except queue.Empty:
            pass
        if buf:
            self.console_write("".join(buf).replace("\r\n", "\n"))
        if end is not None:
            self.console_write("\n[Program finished]\n" if end == 0
                               else "\n[Program finished with an error]\n",
                               None if end == 0 else "err")
        self.root.after(5 if busy else 40, self.poll)

    def stop(self, quiet=False):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            self.token += 1
            if not quiet:
                self.console_write("\n[Stopped]\n", "err")
        self.proc = None

    def send_input(self, ev=None):
        s = self.in_var.get()
        self.in_var.set("")
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write((s + "\n").encode("utf-8"))
                self.proc.stdin.flush()
                self.console_write(s + "\n")
            except OSError:
                pass

    # ---------- Gemini AI assistant ----------
    def ai_write(self, text, tag=None):
        c = self.ai_chat
        c.configure(state="normal")
        c.insert("end", text + "\n", tag)
        c.see("end")
        c.configure(state="disabled")

    def ai_write_md(self, text, base="bot"):
        """Render assistant responses with code blocks, **bold**, `inline code`, and lists."""
        c = self.ai_chat
        c.configure(state="normal")
        for seg in chat_segments(text):
            if seg[0] == "code":
                c.insert("end", seg[2] + "\n", "code")
                continue
            for line in seg[1].strip("\n").split("\n"):
                for txt, tag in md_line(line):
                    c.insert("end", txt, (base, tag) if tag else base)
                c.insert("end", "\n", base)
        c.see("end")
        c.configure(state="disabled")

    def ai_welcome(self):
        self.ai_write("Hello! I'm ScratchPy's programming assistant (Gemini).\n"
                      "Ask me for a program, an explanation, or help fixing an error. "
                      "I can use your current code and console output. "
                      "Requests are sent to the ScratchPy server.", "info")

    def ai_reset(self):
        self.ai_token += 1                      # Ignore any pending response.
        self.ai_history = []
        self.ai_busy = False
        self.ai_btn.configure(state="normal")
        self.ai_chat.configure(state="normal")
        self.ai_chat.delete("1.0", "end")
        self.ai_chat.configure(state="disabled")
        self.ai_welcome()

    def ai_think(self, on):
        c = self.ai_chat
        c.configure(state="normal")
        if on:
            c.mark_set("think", "end-1c")
            c.mark_gravity("think", "left")
            c.insert("end", "⏳ Gemini is thinking…\n", "info")
            c.see("end")
        elif "think" in c.mark_names():
            c.delete("think", "end-1c")
            c.mark_unset("think")
        c.configure(state="disabled")

    def ask_gemini(self, ev=None):
        prompt = self.ai_var.get().strip()
        if not prompt or self.ai_busy:
            return
        self.ai_var.set("")
        self.ai_write("You: " + prompt, "user")
        self.ai_history.append(("user", prompt))
        console = self.console.get("1.0", "end-1c")
        if "Traceback" in console or "terminated with an error" in console:
            self.ai_write("(The console error is being sent with your question.)", "info")
        messages = build_messages(self.ai_history)
        model = self.ai_model.get().strip() or DEFAULT_MODELS[0]
        if model not in DEFAULT_MODELS:
            model = DEFAULT_MODELS[0]
            self.ai_model.set(model)
        if model != self.cfg.get("model"):
            self.cfg["model"] = model
            save_config(self.cfg)
        self.ai_busy = True
        self.ai_btn.configure(state="disabled")
        self.ai_think(True)
        threading.Thread(
            target=self._call_assistant_thread,
            args=(self.ai_token, model, messages, self.current_code(), console),
            daemon=True).start()

    def _call_assistant_thread(self, token, model, messages, code, console):
        try:
            self.ai_q.put((token, "ok", ask_assistant(model, messages, code, console)))
        except AssistantError as ex:
            self.ai_q.put((token, "err", str(ex)))
        except Exception as ex:
            self.ai_q.put((token, "err", "Unexpected error (%s)." % ex.__class__.__name__))

    def ai_poll(self):
        try:
            self._ai_drain()
        except Exception as ex:
            self.ai_write("Internal assistant error: %r" % (ex,), "err")
        self.root.after(100, self.ai_poll)

    def _ai_drain(self):
        while True:
            try:
                token, kind, val = self.ai_q.get_nowait()
            except queue.Empty:
                return
            if token != self.ai_token:           # The chat was reset in the meantime.
                continue
            self.ai_think(False)
            self.ai_busy = False
            self.ai_btn.configure(state="normal")
            if kind == "ok":
                self.ai_history.append(("model", val))
                self.ai_write("Gemini:", "who")
                self.ai_write_md(val)
                self.ai_write("")
                code = last_python_block(val)
                if code:
                    self.suggest_code_injection(code)
            else:
                if self.ai_history and self.ai_history[-1][0] == "user":
                    self.ai_var.set(self.ai_history.pop()[1])      # Restore the prompt so it can be retried.
                self.ai_write(val, "err")

    def set_code_text(self, text):
        """Replace the code pane contents (undoable with Ctrl+Z) and rebuild the blocks."""
        self.code.edit_separator()
        self.code.delete("1.0", "end")
        self.code.insert("1.0", text)
        self.code.edit_separator()
        self.code.edit_modified(False)
        if self._code_job:
            self.root.after_cancel(self._code_job)
            self._code_job = None
        self.apply_code()

    def suggest_code_injection(self, new_code):
        if not messagebox.askyesno("AI assistant", "The assistant suggested code. Apply it to the editor?\n"
                       "(You can undo this later.)", parent=self.root):
            return
        self.ai_backup = self.current_code()
        self.set_code_text(new_code.rstrip("\n") + "\n")
        c = self.ai_chat
        c.configure(state="normal")
        c.insert("end", "✓ Code applied to the editor. ", "info")
        c.insert("end", "[↩ undo]", ("info", "undo"))
        c.insert("end", "\n\n")
        c.see("end")
        c.configure(state="disabled")

    def ai_undo_apply(self, ev=None):
        if self.ai_backup is None:
            return
        old, self.ai_backup = self.ai_backup, None
        self.set_code_text(old)
        self.ai_write("↩ Previous code restored.", "info")
    # ------------------------------------------

    def ask_save_changes(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Save changes?")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        result = {"value": None}

        def finish(value):
            result["value"] = value
            dialog.destroy()

        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Do you want to save your changes before closing?").pack(
            anchor="w", pady=(0, 14))
        buttons = ttk.Frame(body)
        buttons.pack(anchor="e")
        yes = ttk.Button(buttons, text="Yes", command=lambda: finish(True))
        yes.pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="No", command=lambda: finish(False)).pack(
            side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=lambda: finish(None)).pack(side="left")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        dialog.bind("<Escape>", lambda e: finish(None))
        dialog.bind("<Return>", lambda e: finish(True))
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry("+%d+%d" % (max(0, x), max(0, y)))
        dialog.grab_set()
        yes.focus_set()
        dialog.wait_window()
        return result["value"]

    def on_close(self):
        if self.closing:
            return
        save_choice = True
        if self.project_state() != self.saved_state:
            save_choice = self.ask_save_changes()
            if save_choice is None or (save_choice and not self.save_file()):
                return
        if not self.install_update():
            return
        self.closing = True
        if self.autosave_job is not None:
            self.root.after_cancel(self.autosave_job)
            self.autosave_job = None
        if save_choice is False:
            try:
                os.remove(self.autosave_path)
            except FileNotFoundError:
                pass
            except OSError as ex:
                self.autosave_status_var.set("Could not remove autosave: %s" % ex)
        else:
            self.write_autosave()
        self.stop(quiet=True)
        self.root.destroy()


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--run":     # Run a program from the frozen executable.
        sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
        sys.stdout = open(1, "w", encoding="utf-8", buffering=1, closefd=False)
        sys.stderr = open(2, "w", encoding="utf-8", buffering=1, closefd=False)
        script = sys.argv[2]
        sys.argv = [script]
        try:
            runpy.run_path(script, run_name="__main__")
        except SystemExit:
            raise
        except BaseException:
            traceback.print_exc()
            sys.exit(1)
        return
    if sys.platform == "win32":          # Use the application icon in the Windows taskbar.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScratchPy.Blocs")
        except Exception:
            pass
    root = tk.Tk()
    app = App(root)
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py"):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == "__main__":
    main()