#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Version: V26.12
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
import colorsys
import copy
import difflib
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
import tokenize
import threading
import time
import traceback
import unicodedata
import urllib.error
import urllib.request
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

UPDATE_URL = "https://raw.githubusercontent.com/redcat67400-rgb/ScratchPy/program/scratchpy.pyw"
INSTALLER_URL = "https://raw.githubusercontent.com/redcat67400-rgb/ScratchPy/program/install_scratchpy.py"
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


try:
    with open(__file__, "rb") as _source_file:
        APP_VERSION = source_version(_source_file.read(512).decode("utf-8-sig"))
except OSError:                         # Packaged .exe without the embedded source.
    APP_VERSION = None

try:                                    # Optional: smooth (anti-aliased) block outlines.
    from PIL import Image, ImageDraw, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

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
    SPECS[t] = dict(cat=cat, shape=shape, items=items, nfields=n, text=text,
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


# Panels of the right-hand column: key -> (title, minimum height, default share of the height).
RIGHT_PANELS = {"code": ("Python code", 200, 0.334),
                "console": ("Console", 110, 0.299),
                "assistant": ("AI assistant", 200, 0.367)}


def clean_panel_layout(data):
    """Saved layout -> (order, hidden), always valid: every panel exactly once, unknown ones dropped."""
    data = data if isinstance(data, dict) else {}
    order = [k for k in data.get("order", []) if k in RIGHT_PANELS]
    order += [k for k in RIGHT_PANELS if k not in order]
    order = list(dict.fromkeys(order))
    hidden = [k for k in dict.fromkeys(data.get("hidden", [])) if k in RIGHT_PANELS]
    return order, hidden


def panel_sash_positions(order, hidden, height):
    """Sash y positions (one per gap between visible panels) from the default shares."""
    shown = [k for k in order if k not in hidden]
    total = sum(RIGHT_PANELS[k][2] for k in shown) or 1
    pos, acc = [], 0.0
    for k in shown[:-1]:
        acc += RIGHT_PANELS[k][2] / total
        pos.append(int(height * acc))
    return pos


# Colour themes: "light" / "dark" (neutral) and "<colour>-light" / "<colour>-dark".
ACCENTS = {"default": None, "red": 0, "green": 140, "yellow": 45, "blue": 215, "purple": 270}


def split_theme(name):
    """'red-dark' -> ('red', 'dark'); 'dark' -> ('default', 'dark'); None when unknown."""
    if name in ("light", "dark"):
        return "default", name
    accent, _, mode = str(name).partition("-")
    if accent in ACCENTS and accent != "default" and mode in ("light", "dark"):
        return accent, mode
    return None


def join_theme(accent, mode):
    return mode if accent == "default" else "%s-%s" % (accent, mode)


def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l, s)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def theme_palette(name):
    """All interface colours of a theme."""
    accent, mode = split_theme(name) or ("default", "dark")
    hue = ACCENTS[accent]
    if hue is None:                                              # Neutral themes.
        if mode == "dark":
            c = {"BG": "#1e2027", "BG2": "#2b2e38", "EDIT": "#15171c",
                 "FG": "#e4e6eb", "MUTED": "#9aa0aa", "ACCENT": "#4C97FF",
                 "BORDER": "#3a3e4a", "PAL": "#262932", "WS": "#1b1d23",
                 "CONSOLE": "#101216", "CONSOLE_FG": "#d6dae0",
                 "BUTTON_BORDER": "#596171", "SELECT": "#3b4261", "SASH": "#12141a"}
        else:
            c = {"BG": "#f3f5f8", "BG2": "#e5e9ef", "EDIT": "#ffffff",
                 "FG": "#20242b", "MUTED": "#626b78", "ACCENT": "#2563eb",
                 "BORDER": "#c5ccd6", "PAL": "#f7f8fa", "WS": "#edf1f5",
                 "CONSOLE": "#e4e8ed", "CONSOLE_FG": "#20242b",
                 "BUTTON_BORDER": "#98a2b1", "SELECT": "#cbdcff", "SASH": "#d5dbe3"}
        return c
    yellow = accent == "yellow"
    if mode == "dark":
        return {"BG": _hsl(hue, .22, .12), "BG2": _hsl(hue, .20, .18), "EDIT": _hsl(hue, .26, .08),
                "FG": "#eceef2", "MUTED": _hsl(hue, .12, .66),
                "ACCENT": _hsl(hue, .90 if yellow else .72, .55 if yellow else .62),
                "BORDER": _hsl(hue, .15, .27), "PAL": _hsl(hue, .20, .15), "WS": _hsl(hue, .24, .10),
                "CONSOLE": _hsl(hue, .28, .07), "CONSOLE_FG": "#dde0e6",
                "BUTTON_BORDER": _hsl(hue, .16, .40), "SELECT": _hsl(hue, .35, .30),
                "SASH": _hsl(hue, .26, .06)}
    return {"BG": _hsl(hue, .45, .96), "BG2": _hsl(hue, .36, .91), "EDIT": "#ffffff",
            "FG": _hsl(hue, .30, .13), "MUTED": _hsl(hue, .14, .38),
            "ACCENT": _hsl(hue, .90 if yellow else .70, .36 if accent in ("yellow", "green") else .44),
            "BORDER": _hsl(hue, .22, .80), "PAL": _hsl(hue, .45, .975), "WS": _hsl(hue, .42, .94),
            "CONSOLE": _hsl(hue, .32, .92), "CONSOLE_FG": _hsl(hue, .30, .13),
            "BUTTON_BORDER": _hsl(hue, .20, .62), "SELECT": _hsl(hue, .85, .86),
            "SASH": _hsl(hue, .30, .84)}


def diff_lines(old, new):
    """Unified diff as [(tag, text)] with tag in 'add', 'del', 'hunk', 'ctx'."""
    out = []
    for line in difflib.unified_diff(old.splitlines(), new.splitlines(), "current code", "suggested code",
                                     lineterm="", n=2):
        if line.startswith(("---", "+++")):
            continue
        tag = "hunk" if line.startswith("@@") else "add" if line.startswith("+") else \
            "del" if line.startswith("-") else "ctx"
        out.append((tag, line))
    return out


QUICK_PROMPTS = {
    "explain": ("Explain", "Explain this code simply, step by step."),
    "fix": ("Fix", "Find and fix the bugs in this code. Give the complete corrected program."),
    "optimize": ("Optimize", "Simplify and improve this code without changing what it does. "
                             "Give the complete program."),
}


def block_text(b):
    """Searchable text of a block: its label and the text typed in its fields."""
    return (b.spec["label"] + " " + " ".join(str(f) for f in b.fields if not isinstance(f, Block))
            + " " + b.t).lower()


def find_blocks(blocks, query):
    """uids of the blocks matching `query` (case-insensitive), in the order given."""
    q = query.strip().lower()
    return [b.uid for b in blocks if q and q in block_text(b)]


def _lighten(h, k=0.14):
    """Slightly lighter colour (hover effect)."""
    r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(int(c + (255 - c) * k) for c in (r, g, b))


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


# --------------------------------------------------------------------------
# Interface languages
# --------------------------------------------------------------------------
LANGUAGES = [("en", "English"), ("fr", "Français"), ("de", "Deutsch"), ("it", "Italiano"),
             ("ru", "Русский"), ("es", "Español"), ("zh", "中文"), ("ja", "日本語")]
LANG = "en"
_I18N, _I18N_PATTERNS = {}, []
I18N_ROWS = [
    # ---- toolbar ----
    ("▶ Run", "▶ Exécuter", "▶ Starten", "▶ Esegui", "▶ Запуск", "▶ Ejecutar", "▶ 运行", "▶ 実行"),
    ("■ Stop", "■ Arrêter", "■ Stopp", "■ Ferma", "■ Стоп", "■ Detener", "■ 停止", "■ 停止"),
    ("Undo", "Annuler", "Rückgängig", "Annulla", "Отменить", "Deshacer", "撤销", "元に戻す"),
    ("Redo", "Rétablir", "Wiederholen", "Ripeti", "Повторить", "Rehacer", "重做", "やり直し"),
    ("New", "Nouveau", "Neu", "Nuovo", "Новый", "Nuevo", "新建", "新規"),
    ("Open (.py or project)…", "Ouvrir (.py ou projet)…", "Öffnen (.py oder Projekt)…", "Apri (.py o progetto)…",
     "Открыть (.py или проект)…", "Abrir (.py o proyecto)…", "打开（.py 或项目）…", "開く（.py またはプロジェクト）…"),
    ("Save", "Enregistrer", "Speichern", "Salva", "Сохранить", "Guardar", "保存", "保存"),
    ("Save As…", "Enregistrer sous…", "Speichern unter…", "Salva con nome…", "Сохранить как…", "Guardar como…", "另存为…", "名前を付けて保存…"),
    ("Export .py…", "Exporter .py…", ".py exportieren…", "Esporta .py…", "Экспорт .py…", "Exportar .py…", "导出 .py…", ".py を書き出し…"),
    ("Import a library…", "Importer une bibliothèque…", "Bibliothek importieren…", "Importa una libreria…",
     "Импорт библиотеки…", "Importar una biblioteca…", "导入库…", "ライブラリをインポート…"),
    ("Recent ▾", "Récents ▾", "Zuletzt ▾", "Recenti ▾", "Недавние ▾", "Recientes ▾", "最近 ▾", "最近 ▾"),
    ("Examples ▾", "Exemples ▾", "Beispiele ▾", "Esempi ▾", "Примеры ▾", "Ejemplos ▾", "示例 ▾", "サンプル ▾"),
    ("About", "À propos", "Info", "Informazioni", "О программе", "Acerca de", "关于", "概要"),
    ("Panels ▾", "Panneaux ▾", "Bereiche ▾", "Pannelli ▾", "Панели ▾", "Paneles ▾", "面板 ▾", "パネル ▾"),
    ("Zoom:", "Zoom :", "Zoom:", "Zoom:", "Масштаб:", "Zoom:", "缩放：", "ズーム:"),
    ("Zoom in", "Zoom avant", "Vergrößern", "Ingrandisci", "Увеличить", "Acercar", "放大", "拡大"),
    ("Zoom out", "Zoom arrière", "Verkleinern", "Riduci", "Уменьшить", "Alejar", "缩小", "縮小"),
    ("Reset zoom to 100%", "Réinitialiser le zoom à 100 %", "Zoom auf 100 % zurücksetzen", "Reimposta lo zoom al 100%",
     "Сбросить масштаб до 100%", "Restablecer el zoom al 100 %", "将缩放重置为 100%", "ズームを 100% に戻す"),
    ("Run the current program", "Exécuter le programme actuel", "Das aktuelle Programm ausführen", "Esegui il programma corrente",
     "Запустить текущую программу", "Ejecutar el programa actual", "运行当前程序", "現在のプログラムを実行"),
    ("Stop the running program", "Arrêter le programme en cours", "Das laufende Programm anhalten", "Ferma il programma in esecuzione",
     "Остановить выполняющуюся программу", "Detener el programa en ejecución", "停止正在运行的程序", "実行中のプログラムを停止"),
    ("Undo the last edit (Ctrl+Z)", "Annuler la dernière modification (Ctrl+Z)", "Letzte Änderung rückgängig machen (Strg+Z)",
     "Annulla l'ultima modifica (Ctrl+Z)", "Отменить последнее изменение (Ctrl+Z)", "Deshacer la última edición (Ctrl+Z)",
     "撤销上一次编辑 (Ctrl+Z)", "直前の編集を元に戻す (Ctrl+Z)"),
    ("Redo the last undone edit (Ctrl+Y)", "Rétablir la dernière modification annulée (Ctrl+Y)",
     "Letzte rückgängig gemachte Änderung wiederholen (Strg+Y)", "Ripeti l'ultima modifica annullata (Ctrl+Y)",
     "Повторить отменённое изменение (Ctrl+Y)", "Rehacer la última edición deshecha (Ctrl+Y)",
     "重做上一次撤销的编辑 (Ctrl+Y)", "元に戻した編集をやり直す (Ctrl+Y)"),
    ("Create a new project", "Créer un nouveau projet", "Ein neues Projekt erstellen", "Crea un nuovo progetto",
     "Создать новый проект", "Crear un proyecto nuevo", "创建新项目", "新しいプロジェクトを作成"),
    ("Open Python or ScratchPy project", "Ouvrir un fichier Python ou un projet ScratchPy",
     "Python-Datei oder ScratchPy-Projekt öffnen", "Apri un file Python o un progetto ScratchPy",
     "Открыть файл Python или проект ScratchPy", "Abrir un archivo Python o un proyecto de ScratchPy",
     "打开 Python 文件或 ScratchPy 项目", "Python ファイルまたは ScratchPy プロジェクトを開く"),
    ("Save the current project (Ctrl+S)", "Enregistrer le projet actuel (Ctrl+S)", "Aktuelles Projekt speichern (Strg+S)",
     "Salva il progetto corrente (Ctrl+S)", "Сохранить текущий проект (Ctrl+S)", "Guardar el proyecto actual (Ctrl+S)",
     "保存当前项目 (Ctrl+S)", "現在のプロジェクトを保存 (Ctrl+S)"),
    ("Save to a new project file", "Enregistrer dans un nouveau fichier de projet", "In einer neuen Projektdatei speichern",
     "Salva in un nuovo file di progetto", "Сохранить в новый файл проекта", "Guardar en un archivo de proyecto nuevo",
     "保存为新的项目文件", "新しいプロジェクトファイルに保存"),
    ("Export the generated Python code", "Exporter le code Python généré", "Den erzeugten Python-Code exportieren",
     "Esporta il codice Python generato", "Экспортировать сгенерированный код Python", "Exportar el código Python generado",
     "导出生成的 Python 代码", "生成された Python コードを書き出す"),
    ("Add blocks from a Python library", "Ajouter les blocs d'une bibliothèque Python", "Blöcke aus einer Python-Bibliothek hinzufügen",
     "Aggiungi i blocchi di una libreria Python", "Добавить блоки из библиотеки Python", "Añadir bloques de una biblioteca de Python",
     "从 Python 库添加积木", "Python ライブラリのブロックを追加"),
    ("Reopen a recent file", "Rouvrir un fichier récent", "Eine zuletzt verwendete Datei öffnen", "Riapri un file recente",
     "Открыть недавний файл", "Reabrir un archivo reciente", "重新打开最近的文件", "最近のファイルを開く"),
    ("Load a built-in example program", "Charger un programme d'exemple intégré", "Ein integriertes Beispielprogramm laden",
     "Carica un programma di esempio incluso", "Загрузить встроенный пример программы", "Cargar un programa de ejemplo incluido",
     "加载内置示例程序", "内蔵のサンプルプログラムを読み込む"),
    ("Show, hide or reset the panels of the right column", "Afficher, masquer ou réinitialiser les panneaux de la colonne de droite",
     "Bereiche der rechten Spalte ein-/ausblenden oder zurücksetzen", "Mostra, nascondi o reimposta i pannelli della colonna destra",
     "Показать, скрыть или сбросить панели правой колонки", "Mostrar, ocultar o restablecer los paneles de la columna derecha",
     "显示、隐藏或重置右侧栏的面板", "右列のパネルを表示・非表示・リセット"),
    ("ScratchPy - program in Python with blocks", "ScratchPy - programmer en Python avec des blocs",
     "ScratchPy – mit Blöcken in Python programmieren", "ScratchPy - programma in Python con i blocchi",
     "ScratchPy — программирование на Python с помощью блоков", "ScratchPy - programa en Python con bloques",
     "ScratchPy - 用积木编写 Python 程序", "ScratchPy - ブロックで Python プログラミング"),
    # ---- palette / categories ----
    ("Search:", "Recherche :", "Suche:", "Cerca:", "Поиск:", "Buscar:", "搜索：", "検索:"),
    ("Control", "Contrôle", "Steuerung", "Controllo", "Управление", "Control", "控制", "制御"),
    ("Output", "Affichage", "Ausgabe", "Output", "Вывод", "Salida", "输出", "出力"),
    ("Variables", "Variables", "Variablen", "Variabili", "Переменные", "Variables", "变量", "変数"),
    ("Operators", "Opérateurs", "Operatoren", "Operatori", "Операторы", "Operadores", "运算", "演算"),
    ("Functions", "Fonctions", "Funktionen", "Funzioni", "Функции", "Funciones", "函数", "関数"),
    ("Add block: %s", "Ajouter le bloc : %s", "Block hinzufügen: %s", "Aggiungi blocco: %s", "Добавить блок: %s",
     "Añadir bloque: %s", "添加积木：%s", "ブロックを追加: %s"),
    # ---- tabs / settings ----
    ("Workspace", "Espace de travail", "Arbeitsbereich", "Area di lavoro", "Рабочая область", "Área de trabajo", "工作区", "ワークスペース"),
    ("Settings", "Paramètres", "Einstellungen", "Impostazioni", "Настройки", "Ajustes", "设置", "設定"),
    ("Appearance", "Apparence", "Darstellung", "Aspetto", "Оформление", "Apariencia", "外观", "外観"),
    ("Theme", "Thème", "Design", "Tema", "Тема", "Tema", "主题", "テーマ"),
    ("Light", "Clair", "Hell", "Chiaro", "Светлая", "Claro", "浅色", "ライト"),
    ("Dark", "Sombre", "Dunkel", "Scuro", "Тёмная", "Oscuro", "深色", "ダーク"),
    ("Colour", "Couleur", "Farbe", "Colore", "Цвет", "Color", "颜色", "色"),
    ("Default", "Par défaut", "Standard", "Predefinito", "По умолчанию", "Predeterminado", "默认", "標準"),
    ("Red", "Rouge", "Rot", "Rosso", "Красный", "Rojo", "红色", "赤"),
    ("Green", "Vert", "Grün", "Verde", "Зелёный", "Verde", "绿色", "緑"),
    ("Yellow", "Jaune", "Gelb", "Giallo", "Жёлтый", "Amarillo", "黄色", "黄"),
    ("Blue", "Bleu", "Blau", "Blu", "Синий", "Azul", "蓝色", "青"),
    ("Purple", "Violet", "Violett", "Viola", "Фиолетовый", "Morado", "紫色", "紫"),
    ("Language", "Langue", "Sprache", "Lingua", "Язык", "Idioma", "语言", "言語"),
    ("Language changed. Restart ScratchPy to apply it.", "Langue modifiée. Redémarre ScratchPy pour l'appliquer.",
     "Sprache geändert. Starte ScratchPy neu, um sie zu übernehmen.", "Lingua modificata. Riavvia ScratchPy per applicarla.",
     "Язык изменён. Перезапустите ScratchPy, чтобы применить его.", "Idioma cambiado. Reinicia ScratchPy para aplicarlo.",
     "语言已更改。请重新启动 ScratchPy 以生效。", "言語を変更しました。反映するには ScratchPy を再起動してください。"),
    ("Panels (right column)", "Panneaux (colonne de droite)", "Bereiche (rechte Spalte)", "Pannelli (colonna destra)",
     "Панели (правая колонка)", "Paneles (columna derecha)", "面板（右侧栏）", "パネル（右列）"),
    ("Python code", "Code Python", "Python-Code", "Codice Python", "Код Python", "Código Python", "Python 代码", "Python コード"),
    ("Console", "Console", "Konsole", "Console", "Консоль", "Consola", "控制台", "コンソール"),
    ("AI assistant", "Assistant IA", "KI-Assistent", "Assistente IA", "ИИ-ассистент", "Asistente de IA", "AI 助手", "AI アシスタント"),
    ("Show all panels in their default order", "Afficher tous les panneaux dans l'ordre par défaut",
     "Alle Bereiche in der Standardreihenfolge anzeigen", "Mostra tutti i pannelli nell'ordine predefinito",
     "Показать все панели в порядке по умолчанию", "Mostrar todos los paneles en el orden predeterminado",
     "按默认顺序显示所有面板", "すべてのパネルを既定の順序で表示"),
    ("Reset layout", "Réinitialiser la disposition", "Layout zurücksetzen", "Reimposta la disposizione",
     "Сбросить расположение", "Restablecer la disposición", "重置布局", "レイアウトをリセット"),
    ("Automatic save", "Sauvegarde automatique", "Automatisches Speichern", "Salvataggio automatico",
     "Автосохранение", "Guardado automático", "自动保存", "自動保存"),
    ("Backup file", "Fichier de sauvegarde", "Sicherungsdatei", "File di backup", "Файл резервной копии",
     "Archivo de copia", "备份文件", "バックアップファイル"),
    ("Waiting for changes", "En attente de modifications", "Warte auf Änderungen", "In attesa di modifiche",
     "Ожидание изменений", "Esperando cambios", "等待更改", "変更待ち"),
    ("No automatic backup yet", "Aucune sauvegarde automatique pour l'instant", "Noch keine automatische Sicherung",
     "Nessun backup automatico finora", "Автоматических копий пока нет", "Aún no hay copia automática",
     "尚无自动备份", "自動バックアップはまだありません"),
    ("Last backup: %s", "Dernière sauvegarde : %s", "Letzte Sicherung: %s", "Ultimo backup: %s", "Последняя копия: %s",
     "Última copia: %s", "上次备份：%s", "最後のバックアップ: %s"),
    ("Auto-save failed: %s", "Échec de la sauvegarde automatique : %s", "Automatisches Speichern fehlgeschlagen: %s",
     "Salvataggio automatico non riuscito: %s", "Не удалось выполнить автосохранение: %s", "Falló el guardado automático: %s",
     "自动保存失败：%s", "自動保存に失敗しました: %s"),
    ("Could not remove autosave: %s", "Impossible de supprimer la sauvegarde automatique : %s",
     "Automatische Sicherung konnte nicht entfernt werden: %s", "Impossibile rimuovere il salvataggio automatico: %s",
     "Не удалось удалить автосохранение: %s", "No se pudo eliminar el guardado automático: %s",
     "无法删除自动保存：%s", "自動保存を削除できませんでした: %s"),
    # ---- panels ----
    ("Python code (editable)", "Code Python (modifiable)", "Python-Code (bearbeitbar)", "Codice Python (modificabile)",
     "Код Python (редактируемый)", "Código Python (editable)", "Python 代码（可编辑）", "Python コード（編集可）"),
    ("Copy", "Copier", "Kopieren", "Copia", "Копировать", "Copiar", "复制", "コピー"),
    ("Copy generated Python code", "Copier le code Python généré", "Erzeugten Python-Code kopieren", "Copia il codice Python generato",
     "Копировать сгенерированный код Python", "Copiar el código Python generado", "复制生成的 Python 代码", "生成された Python コードをコピー"),
    ("✓ Code and blocks are synchronized", "✓ Le code et les blocs sont synchronisés", "✓ Code und Blöcke sind synchron",
     "✓ Codice e blocchi sono sincronizzati", "✓ Код и блоки синхронизированы", "✓ El código y los bloques están sincronizados",
     "✓ 代码与积木已同步", "✓ コードとブロックは同期しています"),
    ("⚠ Error%s: %s\nBlocks will update when the code is valid.", "⚠ Erreur%s : %s\nLes blocs seront mis à jour quand le code sera valide.",
     "⚠ Fehler%s: %s\nDie Blöcke werden aktualisiert, sobald der Code gültig ist.",
     "⚠ Errore%s: %s\nI blocchi verranno aggiornati quando il codice sarà valido.",
     "⚠ Ошибка%s: %s\nБлоки обновятся, когда код станет корректным.",
     "⚠ Error%s: %s\nLos bloques se actualizarán cuando el código sea válido.",
     "⚠ 错误%s：%s\n代码有效后积木将更新。", "⚠ エラー%s: %s\nコードが有効になるとブロックが更新されます。"),
    ("Hide this panel (Panels menu to show it again)", "Masquer ce panneau (menu Panneaux pour le réafficher)",
     "Diesen Bereich ausblenden (über das Menü Bereiche wieder einblenden)", "Nascondi questo pannello (menu Pannelli per riaprirlo)",
     "Скрыть эту панель (вернуть через меню «Панели»)", "Ocultar este panel (menú Paneles para volver a mostrarlo)",
     "隐藏此面板（可在“面板”菜单中重新显示）", "このパネルを隠す（「パネル」メニューで再表示）"),
    ("Move this panel down", "Descendre ce panneau", "Diesen Bereich nach unten", "Sposta questo pannello in basso",
     "Переместить панель вниз", "Bajar este panel", "下移此面板", "このパネルを下へ"),
    ("Move this panel up", "Monter ce panneau", "Diesen Bereich nach oben", "Sposta questo pannello in alto",
     "Переместить панель вверх", "Subir este panel", "上移此面板", "このパネルを上へ"),
    ("Minimap", "Mini-carte", "Minikarte", "Minimappa", "Миникарта", "Minimapa", "缩略图", "ミニマップ"),
    ("Keyboard shortcuts…", "Raccourcis clavier…", "Tastenkürzel…", "Scorciatoie da tastiera…", "Горячие клавиши…",
     "Atajos de teclado…", "键盘快捷键…", "キーボードショートカット…"),
    ("Console", "Console", "Konsole", "Console", "Консоль", "Consola", "控制台", "コンソール"),
    ("Ask AI to fix", "Demander à l'IA de corriger", "KI um Korrektur bitten", "Chiedi all'IA di correggere",
     "Попросить ИИ исправить", "Pedir a la IA que lo corrija", "让 AI 修复", "AI に修正を依頼"),
    ("Send the error to the AI assistant", "Envoyer l'erreur à l'assistant IA", "Den Fehler an den KI-Assistenten senden",
     "Invia l'errore all'assistente IA", "Отправить ошибку ИИ-ассистенту", "Enviar el error al asistente de IA",
     "将错误发送给 AI 助手", "エラーを AI アシスタントに送る"),
    ("Input:", "Saisie :", "Eingabe:", "Input:", "Ввод:", "Entrada:", "输入：", "入力:"),
    ("Send", "Envoyer", "Senden", "Invia", "Отправить", "Enviar", "发送", "送信"),
    ("Send input to the running program", "Envoyer la saisie au programme en cours", "Eingabe an das laufende Programm senden",
     "Invia l'input al programma in esecuzione", "Отправить ввод работающей программе", "Enviar la entrada al programa en ejecución",
     "向正在运行的程序发送输入", "実行中のプログラムに入力を送る"),
    ("Gemini AI assistant", "Assistant IA Gemini", "Gemini-KI-Assistent", "Assistente IA Gemini", "ИИ-ассистент Gemini",
     "Asistente de IA Gemini", "Gemini AI 助手", "Gemini AI アシスタント"),
    ("New chat", "Nouvelle discussion", "Neuer Chat", "Nuova chat", "Новый чат", "Nuevo chat", "新对话", "新しいチャット"),
    ("Clear the assistant conversation", "Effacer la conversation avec l'assistant", "Die Unterhaltung mit dem Assistenten löschen",
     "Cancella la conversazione con l'assistente", "Очистить разговор с ассистентом", "Borrar la conversación con el asistente",
     "清除与助手的对话", "アシスタントとの会話を消去"),
    ("Model:", "Modèle :", "Modell:", "Modello:", "Модель:", "Modelo:", "模型：", "モデル:"),
    ("Quick:", "Rapide :", "Schnell:", "Rapido:", "Быстро:", "Rápido:", "快捷：", "クイック:"),
    ("Explain", "Expliquer", "Erklären", "Spiega", "Объяснить", "Explicar", "解释", "説明"),
    ("Fix", "Corriger", "Beheben", "Correggi", "Исправить", "Corregir", "修复", "修正"),
    ("Optimize", "Optimiser", "Optimieren", "Ottimizza", "Оптимизировать", "Optimizar", "优化", "最適化"),
    ("%s the selected code (or the whole program if nothing is selected)",
     "%s le code sélectionné (ou tout le programme si rien n'est sélectionné)",
     "%s den ausgewählten Code (oder das ganze Programm, wenn nichts ausgewählt ist)",
     "%s il codice selezionato (o l'intero programma se nulla è selezionato)",
     "%s выделенный код (или всю программу, если ничего не выделено)",
     "%s el código seleccionado (o todo el programa si no hay selección)",
     "%s所选代码（未选择时为整个程序）", "%s 選択したコード（未選択なら全体）"),
    ("Prompt:", "Demande :", "Anfrage:", "Richiesta:", "Запрос:", "Consulta:", "提示：", "プロンプト:"),
    ("Ask", "Demander", "Fragen", "Chiedi", "Спросить", "Preguntar", "提问", "質問"),
    ("Send your question to the programming assistant", "Envoyer ta question à l'assistant de programmation",
     "Deine Frage an den Programmierassistenten senden", "Invia la tua domanda all'assistente di programmazione",
     "Отправить вопрос ассистенту по программированию", "Enviar tu pregunta al asistente de programación",
     "将问题发送给编程助手", "プログラミングアシスタントに質問を送る"),
    ("Hello! I'm ScratchPy's programming assistant (Gemini).\nAsk me for a program, an explanation, or help fixing an error. I can use your current code and console output. Requests are sent to the ScratchPy server.",
     "Bonjour ! Je suis l'assistant de programmation de ScratchPy (Gemini).\nDemande-moi un programme, une explication ou de l'aide pour corriger une erreur. Je peux utiliser ton code actuel et la sortie de la console. Les requêtes sont envoyées au serveur ScratchPy.",
     "Hallo! Ich bin der Programmierassistent von ScratchPy (Gemini).\nFrag mich nach einem Programm, einer Erklärung oder Hilfe bei einem Fehler. Ich kann deinen aktuellen Code und die Konsolenausgabe nutzen. Anfragen werden an den ScratchPy-Server gesendet.",
     "Ciao! Sono l'assistente di programmazione di ScratchPy (Gemini).\nChiedimi un programma, una spiegazione o aiuto per correggere un errore. Posso usare il tuo codice attuale e l'output della console. Le richieste vengono inviate al server di ScratchPy.",
     "Здравствуйте! Я ассистент по программированию ScratchPy (Gemini).\nПросите у меня программу, объяснение или помощь с исправлением ошибки. Я могу использовать ваш код и вывод консоли. Запросы отправляются на сервер ScratchPy.",
     "¡Hola! Soy el asistente de programación de ScratchPy (Gemini).\nPídeme un programa, una explicación o ayuda para corregir un error. Puedo usar tu código actual y la salida de la consola. Las solicitudes se envían al servidor de ScratchPy.",
     "你好！我是 ScratchPy 的编程助手（Gemini）。\n你可以向我索取程序、解释，或让我帮忙修复错误。我可以使用你当前的代码和控制台输出。请求会发送到 ScratchPy 服务器。",
     "こんにちは！ScratchPy のプログラミングアシスタント（Gemini）です。\nプログラム、説明、エラー修正の手伝いなどを頼んでください。現在のコードとコンソール出力を使えます。リクエストは ScratchPy サーバーに送信されます。"),
    # ---- welcome ----
    ("Start your program", "Commence ton programme", "Starte dein Programm", "Inizia il tuo programma", "Начните свою программу",
     "Empieza tu programa", "开始你的程序", "プログラムを始めましょう"),
    ("Drag a block from the palette to get started", "Fais glisser un bloc depuis la palette pour commencer",
     "Ziehe einen Block aus der Palette, um zu beginnen", "Trascina un blocco dalla tavolozza per iniziare",
     "Перетащите блок из палитры, чтобы начать", "Arrastra un bloque desde la paleta para empezar",
     "从积木栏拖出一个积木即可开始", "パレットからブロックをドラッグして始めましょう"),
    ("or press Ctrl + O to open a file", "ou appuie sur Ctrl + O pour ouvrir un fichier", "oder drücke Strg + O, um eine Datei zu öffnen",
     "oppure premi Ctrl + O per aprire un file", "или нажмите Ctrl + O, чтобы открыть файл", "o pulsa Ctrl + O para abrir un archivo",
     "或按 Ctrl + O 打开文件", "または Ctrl + O でファイルを開きます"),
    # ---- find bar / context menus ----
    ("Find:", "Rechercher :", "Suchen:", "Trova:", "Найти:", "Buscar:", "查找：", "検索:"),
    ("Close search (Esc)", "Fermer la recherche (Échap)", "Suche schließen (Esc)", "Chiudi la ricerca (Esc)",
     "Закрыть поиск (Esc)", "Cerrar la búsqueda (Esc)", "关闭搜索 (Esc)", "検索を閉じる (Esc)"),
    ("Duplicate", "Dupliquer", "Duplizieren", "Duplica", "Дублировать", "Duplicar", "复制一份", "複製"),
    ("Delete this block", "Supprimer ce bloc", "Diesen Block löschen", "Elimina questo blocco", "Удалить этот блок",
     "Eliminar este bloque", "删除此积木", "このブロックを削除"),
    ("Duplicate selection (%d blocks)", "Dupliquer la sélection (%d blocs)", "Auswahl duplizieren (%d Blöcke)",
     "Duplica la selezione (%d blocchi)", "Дублировать выделение (блоков: %d)", "Duplicar la selección (%d bloques)",
     "复制所选内容（%d 个积木）", "選択を複製（%d ブロック）"),
    ("Delete selection", "Supprimer la sélection", "Auswahl löschen", "Elimina la selezione", "Удалить выделение",
     "Eliminar la selección", "删除所选内容", "選択を削除"),
    ("Deselect all", "Tout désélectionner", "Auswahl aufheben", "Deseleziona tutto", "Снять выделение",
     "Deseleccionar todo", "取消全部选择", "選択をすべて解除"),
    # ---- recent / examples / shortcuts ----
    ("(no recent files)", "(aucun fichier récent)", "(keine zuletzt verwendeten Dateien)", "(nessun file recente)",
     "(нет недавних файлов)", "(sin archivos recientes)", "（没有最近的文件）", "（最近のファイルはありません）"),
    ("Clear the list", "Vider la liste", "Liste leeren", "Svuota l'elenco", "Очистить список", "Vaciar la lista", "清空列表", "リストを消去"),
    ("Sum and comparison", "Somme et comparaison", "Summe und Vergleich", "Somma e confronto", "Сумма и сравнение",
     "Suma y comparación", "求和与比较", "合計と比較"),
    ("Guess the number", "Devine le nombre", "Zahlenraten", "Indovina il numero", "Угадай число", "Adivina el número", "猜数字", "数当てゲーム"),
    ("Calculator", "Calculatrice", "Taschenrechner", "Calcolatrice", "Калькулятор", "Calculadora", "计算器", "電卓"),
    ("Multiplication table", "Table de multiplication", "Einmaleins", "Tabellina", "Таблица умножения", "Tabla de multiplicar", "乘法表", "九九の表"),
    ("FizzBuzz", "FizzBuzz", "FizzBuzz", "FizzBuzz", "FizzBuzz", "FizzBuzz", "FizzBuzz", "FizzBuzz"),
    ("Greeting function", "Fonction de salutation", "Begrüßungsfunktion", "Funzione di saluto", "Функция приветствия",
     "Función de saludo", "问候函数", "あいさつ関数"),
    ("Examples", "Exemples", "Beispiele", "Esempi", "Примеры", "Ejemplos", "示例", "サンプル"),
    ("Replace the current blocks with the example '%s'?", "Remplacer les blocs actuels par l'exemple « %s » ?",
     "Aktuelle Blöcke durch das Beispiel „%s“ ersetzen?", "Sostituire i blocchi attuali con l'esempio «%s»?",
     "Заменить текущие блоки примером «%s»?", "¿Reemplazar los bloques actuales por el ejemplo «%s»?",
     "用示例“%s”替换当前的积木？", "現在のブロックをサンプル「%s」に置き換えますか？"),
    ("Could not load the example:\n%s", "Impossible de charger l'exemple :\n%s", "Das Beispiel konnte nicht geladen werden:\n%s",
     "Impossibile caricare l'esempio:\n%s", "Не удалось загрузить пример:\n%s", "No se pudo cargar el ejemplo:\n%s",
     "无法加载示例：\n%s", "サンプルを読み込めませんでした:\n%s"),
    ("Keyboard shortcuts", "Raccourcis clavier", "Tastenkürzel", "Scorciatoie da tastiera", "Горячие клавиши",
     "Atajos de teclado", "键盘快捷键", "キーボードショートカット"),
    ("Customizable shortcuts", "Raccourcis personnalisables", "Anpassbare Tastenkürzel", "Scorciatoie personalizzabili",
     "Настраиваемые сочетания", "Atajos personalizables", "可自定义的快捷键", "カスタマイズ可能なショートカット"),
    ("Fixed shortcuts", "Raccourcis fixes", "Feste Tastenkürzel", "Scorciatoie fisse", "Фиксированные сочетания",
     "Atajos fijos", "固定快捷键", "固定のショートカット"),
    ("Reset to defaults", "Rétablir les valeurs par défaut", "Auf Standard zurücksetzen", "Ripristina i valori predefiniti",
     "Сбросить по умолчанию", "Restablecer valores predeterminados", "恢复默认", "既定値に戻す"),
    ("Press a key…", "Appuie sur une touche…", "Taste drücken…", "Premi un tasto…", "Нажмите клавишу…", "Pulsa una tecla…",
     "请按一个键…", "キーを押してください…"),
    ("%s is already used by “%s”.", "%s est déjà utilisé par « %s ».", "%s wird bereits von „%s“ verwendet.",
     "%s è già usato da «%s».", "%s уже используется для «%s».", "%s ya lo usa «%s».", "%s 已被“%s”使用。", "%s は「%s」で既に使われています。"),
    ("Run the program", "Exécuter le programme", "Programm starten", "Esegui il programma", "Запустить программу",
     "Ejecutar el programa", "运行程序", "プログラムを実行"),
    ("Stop the program", "Arrêter le programme", "Programm anhalten", "Ferma il programma", "Остановить программу",
     "Detener el programa", "停止程序", "プログラムを停止"),
    ("New project", "Nouveau projet", "Neues Projekt", "Nuovo progetto", "Новый проект", "Proyecto nuevo", "新建项目", "新規プロジェクト"),
    ("Open a file", "Ouvrir un fichier", "Datei öffnen", "Apri un file", "Открыть файл", "Abrir un archivo", "打开文件", "ファイルを開く"),
    ("Save the project", "Enregistrer le projet", "Projekt speichern", "Salva il progetto", "Сохранить проект",
     "Guardar el proyecto", "保存项目", "プロジェクトを保存"),
    ("Search the workspace", "Rechercher dans l'espace de travail", "Arbeitsbereich durchsuchen", "Cerca nell'area di lavoro",
     "Поиск в рабочей области", "Buscar en el área de trabajo", "在工作区中搜索", "ワークスペースを検索"),
    ("Next search result", "Résultat suivant", "Nächster Treffer", "Risultato successivo", "Следующий результат",
     "Siguiente resultado", "下一个结果", "次の検索結果"),
    ("Previous search result", "Résultat précédent", "Vorheriger Treffer", "Risultato precedente", "Предыдущий результат",
     "Resultado anterior", "上一个结果", "前の検索結果"),
    ("Show the shortcuts", "Afficher les raccourcis", "Tastenkürzel anzeigen", "Mostra le scorciatoie", "Показать сочетания клавиш",
     "Mostrar los atajos", "显示快捷键", "ショートカットを表示"),
    ("Undo / redo", "Annuler / rétablir", "Rückgängig / Wiederholen", "Annulla / ripeti", "Отменить / повторить",
     "Deshacer / rehacer", "撤销 / 重做", "元に戻す / やり直し"),
    ("Select all blocks", "Sélectionner tous les blocs", "Alle Blöcke auswählen", "Seleziona tutti i blocchi",
     "Выделить все блоки", "Seleccionar todos los bloques", "选择全部积木", "すべてのブロックを選択"),
    ("Copy / paste the selected blocks", "Copier / coller les blocs sélectionnés", "Ausgewählte Blöcke kopieren / einfügen",
     "Copia / incolla i blocchi selezionati", "Копировать / вставить выделенные блоки", "Copiar / pegar los bloques seleccionados",
     "复制 / 粘贴所选积木", "選択したブロックをコピー / 貼り付け"),
    ("Duplicate the selected blocks", "Dupliquer les blocs sélectionnés", "Ausgewählte Blöcke duplizieren",
     "Duplica i blocchi selezionati", "Дублировать выделенные блоки", "Duplicar los bloques seleccionados",
     "复制所选积木", "選択したブロックを複製"),
    ("Delete the selected blocks", "Supprimer les blocs sélectionnés", "Ausgewählte Blöcke löschen",
     "Elimina i blocchi selezionati", "Удалить выделенные блоки", "Eliminar los bloques seleccionados",
     "删除所选积木", "選択したブロックを削除"),
    ("Zoom", "Zoom", "Zoom", "Zoom", "Масштаб", "Zoom", "缩放", "ズーム"),
    # ---- about / updates ----
    ("About ScratchPy", "À propos de ScratchPy", "Über ScratchPy", "Informazioni su ScratchPy", "О программе ScratchPy",
     "Acerca de ScratchPy", "关于 ScratchPy", "ScratchPy について"),
    ("Version %s", "Version %s", "Version %s", "Versione %s", "Версия %s", "Versión %s", "版本 %s", "バージョン %s"),
    ("Check for updates", "Rechercher des mises à jour", "Nach Updates suchen", "Cerca aggiornamenti", "Проверить обновления",
     "Buscar actualizaciones", "检查更新", "更新を確認"),
    ("Check GitHub for a newer ScratchPy version", "Chercher une version plus récente de ScratchPy sur GitHub",
     "Auf GitHub nach einer neueren ScratchPy-Version suchen", "Cerca su GitHub una versione più recente di ScratchPy",
     "Проверить на GitHub наличие новой версии ScratchPy", "Buscar en GitHub una versión más reciente de ScratchPy",
     "在 GitHub 上检查 ScratchPy 新版本", "GitHub で ScratchPy の新しいバージョンを確認"),
    ("Open the ScratchPy GitHub repository", "Ouvrir le dépôt GitHub de ScratchPy", "Das ScratchPy-GitHub-Repository öffnen",
     "Apri il repository GitHub di ScratchPy", "Открыть репозиторий ScratchPy на GitHub", "Abrir el repositorio de ScratchPy en GitHub",
     "打开 ScratchPy 的 GitHub 仓库", "ScratchPy の GitHub リポジトリを開く"),
    ("Close", "Fermer", "Schließen", "Chiudi", "Закрыть", "Cerrar", "关闭", "閉じる"),
    ("Updates", "Mises à jour", "Updates", "Aggiornamenti", "Обновления", "Actualizaciones", "更新", "アップデート"),
    ("Update", "Mise à jour", "Update", "Aggiornamento", "Обновление", "Actualización", "更新", "アップデート"),
    ("Update available", "Mise à jour disponible", "Update verfügbar", "Aggiornamento disponibile", "Доступно обновление",
     "Actualización disponible", "有可用更新", "アップデートがあります"),
    ("ScratchPy %s is available. You are using %s. Install the update now?",
     "ScratchPy %s est disponible. Tu utilises la version %s. Installer la mise à jour maintenant ?",
     "ScratchPy %s ist verfügbar. Du verwendest %s. Update jetzt installieren?",
     "ScratchPy %s è disponibile. Stai usando la %s. Installare ora l'aggiornamento?",
     "Доступна ScratchPy %s. Вы используете %s. Установить обновление сейчас?",
     "ScratchPy %s está disponible. Estás usando %s. ¿Instalar la actualización ahora?",
     "ScratchPy %s 已发布，你正在使用 %s。现在安装更新吗？", "ScratchPy %s が利用可能です（現在 %s）。今すぐ更新しますか？"),
    ("ScratchPy %s is up to date.", "ScratchPy %s est à jour.", "ScratchPy %s ist auf dem neuesten Stand.",
     "ScratchPy %s è aggiornato.", "ScratchPy %s — актуальная версия.", "ScratchPy %s está actualizado.",
     "ScratchPy %s 已是最新版本。", "ScratchPy %s は最新です。"),
    ("Could not check for updates:\n%s", "Impossible de rechercher les mises à jour :\n%s", "Update-Suche fehlgeschlagen:\n%s",
     "Impossibile cercare aggiornamenti:\n%s", "Не удалось проверить обновления:\n%s", "No se pudo buscar actualizaciones:\n%s",
     "无法检查更新：\n%s", "更新を確認できませんでした:\n%s"),
    ("Update checks are available on Windows only.", "La recherche de mises à jour n'est disponible que sous Windows.",
     "Die Update-Suche ist nur unter Windows verfügbar.", "La ricerca di aggiornamenti è disponibile solo su Windows.",
     "Проверка обновлений доступна только в Windows.", "La búsqueda de actualizaciones solo está disponible en Windows.",
     "仅 Windows 支持检查更新。", "更新の確認は Windows でのみ利用できます。"),
    ("Updates are not supported by this packaged build.", "Cette version empaquetée ne gère pas les mises à jour.",
     "Diese gepackte Version unterstützt keine Updates.", "Questa versione pacchettizzata non supporta gli aggiornamenti.",
     "Эта упакованная сборка не поддерживает обновления.", "Esta versión empaquetada no admite actualizaciones.",
     "此打包版本不支持更新。", "このパッケージ版は更新に対応していません。"),
    ("An update check is already in progress.", "Une recherche de mise à jour est déjà en cours.",
     "Eine Update-Suche läuft bereits.", "Una ricerca di aggiornamenti è già in corso.",
     "Проверка обновлений уже выполняется.", "Ya hay una búsqueda de actualizaciones en curso.",
     "已在检查更新。", "更新の確認はすでに実行中です。"),
    ("Could not start the updater:\n%s", "Impossible de lancer la mise à jour :\n%s", "Der Updater konnte nicht gestartet werden:\n%s",
     "Impossibile avviare l'aggiornamento:\n%s", "Не удалось запустить обновление:\n%s", "No se pudo iniciar el actualizador:\n%s",
     "无法启动更新程序：\n%s", "アップデーターを起動できませんでした:\n%s"),
    ("Could not start the installed updater:\n%s", "Impossible de lancer la mise à jour installée :\n%s",
     "Der installierte Updater konnte nicht gestartet werden:\n%s", "Impossibile avviare l'aggiornatore installato:\n%s",
     "Не удалось запустить установленный модуль обновления:\n%s", "No se pudo iniciar el actualizador instalado:\n%s",
     "无法启动已安装的更新程序：\n%s", "インストール済みのアップデーターを起動できませんでした:\n%s"),
    # ---- dialogs ----
    ("OK", "OK", "OK", "OK", "ОК", "Aceptar", "确定", "OK"),
    ("Cancel", "Annuler", "Abbrechen", "Annulla", "Отмена", "Cancelar", "取消", "キャンセル"),
    ("Yes", "Oui", "Ja", "Sì", "Да", "Sí", "是", "はい"),
    ("No", "Non", "Nein", "No", "Нет", "No", "否", "いいえ"),
    ("Import a library", "Importer une bibliothèque", "Bibliothek importieren", "Importa una libreria", "Импорт библиотеки",
     "Importar una biblioteca", "导入库", "ライブラリをインポート"),
    ("Python module name (e.g. math, random, string, os.path, turtle, numpy):",
     "Nom du module Python (ex. math, random, string, os.path, turtle, numpy) :",
     "Name des Python-Moduls (z. B. math, random, string, os.path, turtle, numpy):",
     "Nome del modulo Python (es. math, random, string, os.path, turtle, numpy):",
     "Имя модуля Python (например, math, random, string, os.path, turtle, numpy):",
     "Nombre del módulo de Python (p. ej. math, random, string, os.path, turtle, numpy):",
     "Python 模块名称（例如 math、random、string、os.path、turtle、numpy）：",
     "Python モジュール名（例: math, random, string, os.path, turtle, numpy）:"),
    ("Library not found", "Bibliothèque introuvable", "Bibliothek nicht gefunden", "Libreria non trovata", "Библиотека не найдена",
     "Biblioteca no encontrada", "未找到库", "ライブラリが見つかりません"),
    ("'%s' is not installed.\nEnter the package name to install with pip (leave blank to cancel):",
     "« %s » n'est pas installé.\nSaisis le nom du paquet à installer avec pip (laisse vide pour annuler) :",
     "„%s“ ist nicht installiert.\nGib den Paketnamen für die Installation mit pip ein (leer lassen zum Abbrechen):",
     "«%s» non è installato.\nInserisci il nome del pacchetto da installare con pip (lascia vuoto per annullare):",
     "«%s» не установлен.\nВведите имя пакета для установки через pip (оставьте пустым для отмены):",
     "«%s» no está instalado.\nIntroduce el nombre del paquete para instalar con pip (déjalo vacío para cancelar):",
     "未安装“%s”。\n请输入要用 pip 安装的包名（留空则取消）：", "「%s」はインストールされていません。\npip でインストールするパッケージ名を入力してください（空欄でキャンセル）:"),
    ("Import", "Importer", "Importieren", "Importa", "Импорт", "Importar", "导入", "インポート"),
    ("Could not import '%s':\n%s", "Impossible d'importer « %s » :\n%s", "„%s“ konnte nicht importiert werden:\n%s",
     "Impossibile importare «%s»:\n%s", "Не удалось импортировать «%s»:\n%s", "No se pudo importar «%s»:\n%s",
     "无法导入“%s”：\n%s", "「%s」をインポートできませんでした:\n%s"),
    ("pip", "pip", "pip", "pip", "pip", "pip", "pip", "pip"),
    ("Installation failed:\n%s", "Échec de l'installation :\n%s", "Installation fehlgeschlagen:\n%s", "Installazione non riuscita:\n%s",
     "Не удалось установить:\n%s", "Falló la instalación:\n%s", "安装失败：\n%s", "インストールに失敗しました:\n%s"),
    ("'%s' is not included in this .exe application.\nUse scratchpy.py with Python, or rebuild the .exe with --hidden-import %s.",
     "« %s » n'est pas inclus dans cette application .exe.\nUtilise scratchpy.py avec Python, ou reconstruis le .exe avec --hidden-import %s.",
     "„%s“ ist in dieser .exe-Anwendung nicht enthalten.\nVerwende scratchpy.py mit Python oder erstelle die .exe mit --hidden-import %s neu.",
     "«%s» non è incluso in questa applicazione .exe.\nUsa scratchpy.py con Python oppure ricrea l'.exe con --hidden-import %s.",
     "«%s» не включён в это приложение .exe.\nИспользуйте scratchpy.py с Python или пересоберите .exe с --hidden-import %s.",
     "«%s» no está incluido en esta aplicación .exe.\nUsa scratchpy.py con Python o vuelve a compilar el .exe con --hidden-import %s.",
     "此 .exe 应用程序不包含“%s”。\n请用 Python 运行 scratchpy.py，或使用 --hidden-import %s 重新构建 .exe。",
     "「%s」はこの .exe アプリに含まれていません。\nPython で scratchpy.py を使うか、--hidden-import %s を付けて .exe をビルドし直してください。"),
    ("Clear the current project (blocks and imported libraries)?", "Effacer le projet actuel (blocs et bibliothèques importées) ?",
     "Das aktuelle Projekt (Blöcke und importierte Bibliotheken) löschen?", "Cancellare il progetto corrente (blocchi e librerie importate)?",
     "Очистить текущий проект (блоки и импортированные библиотеки)?", "¿Borrar el proyecto actual (bloques y bibliotecas importadas)?",
     "清除当前项目（积木和已导入的库）？", "現在のプロジェクト（ブロックとインポート済みライブラリ）を消去しますか？"),
    ("Save project", "Enregistrer le projet", "Projekt speichern", "Salva progetto", "Сохранение проекта", "Guardar proyecto", "保存项目", "プロジェクトの保存"),
    ("Could not save the project:\n%s", "Impossible d'enregistrer le projet :\n%s", "Das Projekt konnte nicht gespeichert werden:\n%s",
     "Impossibile salvare il progetto:\n%s", "Не удалось сохранить проект:\n%s", "No se pudo guardar el proyecto:\n%s",
     "无法保存项目：\n%s", "プロジェクトを保存できませんでした:\n%s"),
    ("Open", "Ouvrir", "Öffnen", "Apri", "Открыть", "Abrir", "打开", "開く"),
    ("Syntax error in this Python file (line %s):\n%s", "Erreur de syntaxe dans ce fichier Python (ligne %s) :\n%s",
     "Syntaxfehler in dieser Python-Datei (Zeile %s):\n%s", "Errore di sintassi in questo file Python (riga %s):\n%s",
     "Синтаксическая ошибка в этом файле Python (строка %s):\n%s", "Error de sintaxis en este archivo de Python (línea %s):\n%s",
     "此 Python 文件有语法错误（第 %s 行）：\n%s", "この Python ファイルに構文エラーがあります（%s 行目）:\n%s"),
    ("Could not read the file:\n%s", "Impossible de lire le fichier :\n%s", "Die Datei konnte nicht gelesen werden:\n%s",
     "Impossibile leggere il file:\n%s", "Не удалось прочитать файл:\n%s", "No se pudo leer el archivo:\n%s",
     "无法读取文件：\n%s", "ファイルを読み込めませんでした:\n%s"),
    ("Invalid file:\n%s", "Fichier invalide :\n%s", "Ungültige Datei:\n%s", "File non valido:\n%s", "Недопустимый файл:\n%s",
     "Archivo no válido:\n%s", "无效文件：\n%s", "無効なファイルです:\n%s"),
    ("Large file", "Fichier volumineux", "Große Datei", "File di grandi dimensioni", "Большой файл", "Archivo grande", "大文件", "大きなファイル"),
    ("This file will create more than 2,500 blocks and may be slow. Continue?",
     "Ce fichier créera plus de 2 500 blocs et peut être lent. Continuer ?",
     "Diese Datei erzeugt mehr als 2.500 Blöcke und kann langsam sein. Fortfahren?",
     "Questo file creerà più di 2.500 blocchi e potrebbe essere lento. Continuare?",
     "Этот файл создаст более 2 500 блоков и может работать медленно. Продолжить?",
     "Este archivo creará más de 2.500 bloques y puede ser lento. ¿Continuar?",
     "此文件将创建超过 2,500 个积木，可能较慢。继续吗？", "このファイルは 2,500 個を超えるブロックを作成し、動作が遅くなる可能性があります。続行しますか？"),
    ("Local module", "Module local", "Lokales Modul", "Modulo locale", "Локальный модуль", "Módulo local", "本地模块", "ローカルモジュール"),
    ("This file imports '%s', a module located beside it.\nCreating its blocks will execute it in the editor. Continue?",
     "Ce fichier importe « %s », un module situé à côté.\nCréer ses blocs l'exécutera dans l'éditeur. Continuer ?",
     "Diese Datei importiert „%s“, ein Modul im selben Ordner.\nDas Erstellen seiner Blöcke führt es im Editor aus. Fortfahren?",
     "Questo file importa «%s», un modulo che si trova accanto.\nCreare i suoi blocchi lo eseguirà nell'editor. Continuare?",
     "Этот файл импортирует «%s» — модуль, лежащий рядом.\nСоздание его блоков выполнит его в редакторе. Продолжить?",
     "Este archivo importa «%s», un módulo situado junto a él.\nCrear sus bloques lo ejecutará en el editor. ¿Continuar?",
     "此文件导入了同目录下的模块“%s”。\n创建其积木会在编辑器中执行该模块。继续吗？",
     "このファイルは隣にあるモジュール「%s」をインポートしています。\nブロックを作成するとエディターで実行されます。続行しますか？"),
    ("Drop a Python (.py) file or a ScratchPy project (.json).", "Dépose un fichier Python (.py) ou un projet ScratchPy (.json).",
     "Ziehe eine Python-Datei (.py) oder ein ScratchPy-Projekt (.json) hierher.", "Trascina un file Python (.py) o un progetto ScratchPy (.json).",
     "Перетащите файл Python (.py) или проект ScratchPy (.json).", "Suelta un archivo de Python (.py) o un proyecto de ScratchPy (.json).",
     "请拖入 Python (.py) 文件或 ScratchPy 项目 (.json)。", "Python (.py) ファイルまたは ScratchPy プロジェクト (.json) をドロップしてください。"),
    ("Restore autosave?", "Restaurer la sauvegarde automatique ?", "Automatische Sicherung wiederherstellen?",
     "Ripristinare il salvataggio automatico?", "Восстановить автосохранение?", "¿Restaurar el guardado automático?",
     "恢复自动保存？", "自動保存を復元しますか？"),
    ("An automatically saved project was found. Restore it?", "Un projet sauvegardé automatiquement a été trouvé. Le restaurer ?",
     "Ein automatisch gespeichertes Projekt wurde gefunden. Wiederherstellen?", "È stato trovato un progetto salvato automaticamente. Ripristinarlo?",
     "Найден автоматически сохранённый проект. Восстановить его?", "Se encontró un proyecto guardado automáticamente. ¿Restaurarlo?",
     "发现了自动保存的项目。是否恢复？", "自動保存されたプロジェクトが見つかりました。復元しますか？"),
    ("Save changes?", "Enregistrer les modifications ?", "Änderungen speichern?", "Salvare le modifiche?", "Сохранить изменения?",
     "¿Guardar los cambios?", "保存更改？", "変更を保存しますか？"),
    ("Do you want to save your changes before closing?", "Veux-tu enregistrer tes modifications avant de fermer ?",
     "Möchtest du deine Änderungen vor dem Schließen speichern?", "Vuoi salvare le modifiche prima di chiudere?",
     "Сохранить изменения перед закрытием?", "¿Quieres guardar los cambios antes de cerrar?",
     "关闭前要保存更改吗？", "閉じる前に変更を保存しますか？"),
    ("Review the suggested changes", "Vérifier les modifications proposées", "Vorgeschlagene Änderungen prüfen",
     "Controlla le modifiche suggerite", "Проверьте предложенные изменения", "Revisa los cambios sugeridos",
     "查看建议的更改", "提案された変更を確認"),
    ("Lines in red will be removed, lines in green will be added.", "Les lignes en rouge seront supprimées, celles en vert seront ajoutées.",
     "Rote Zeilen werden entfernt, grüne Zeilen werden hinzugefügt.", "Le righe in rosso verranno rimosse, quelle in verde aggiunte.",
     "Красные строки будут удалены, зелёные — добавлены.", "Las líneas en rojo se eliminarán y las verdes se añadirán.",
     "红色行将被删除，绿色行将被添加。", "赤い行は削除され、緑の行は追加されます。"),
    ("Apply", "Appliquer", "Anwenden", "Applica", "Применить", "Aplicar", "应用", "適用"),
    ("The suggested code is identical to your code.", "Le code proposé est identique au tien.", "Der vorgeschlagene Code ist identisch mit deinem.",
     "Il codice suggerito è identico al tuo.", "Предложенный код совпадает с вашим.", "El código sugerido es idéntico al tuyo.",
     "建议的代码与你的代码相同。", "提案されたコードは現在のコードと同じです。"),
    ("GitHub", "GitHub", "GitHub", "GitHub", "GitHub", "GitHub", "GitHub", "GitHub"),
    ("ScratchPy", "ScratchPy", "ScratchPy", "ScratchPy", "ScratchPy", "ScratchPy", "ScratchPy", "ScratchPy"),
]

# Block templates ("{}" marks a field). Same number of "{}" in every language.
I18N_BLOCKS = [
    ("when ▶ clicked", "quand ▶ cliqué", "Wenn ▶ angeklickt", "quando si clicca ▶", "когда нажат ▶", "al hacer clic en ▶", "当 ▶ 被点击", "▶ が押されたとき"),
    ("repeat {} times", "répéter {} fois", "wiederhole {} Mal", "ripeti {} volte", "повторить {} раз", "repetir {} veces", "重复 {} 次", "{} 回繰り返す"),
    ("for {} in {}", "pour {} dans {}", "für {} in {}", "per {} in {}", "для {} в {}", "para {} en {}", "对于 {} 在 {} 中", "{} を {} で繰り返す"),
    ("while {}", "tant que {}", "solange {}", "finché {}", "пока {}", "mientras {}", "当 {}", "{} の間"),
    ("forever", "indéfiniment", "für immer", "per sempre", "всегда", "para siempre", "重复执行", "ずっと"),
    ("if {} then", "si {} alors", "falls {} dann", "se {} allora", "если {} то", "si {} entonces", "如果 {} 那么", "もし {} なら"),
    ("else if {} then", "sinon si {} alors", "sonst falls {} dann", "altrimenti se {} allora", "иначе если {} то", "si no, si {} entonces", "否则如果 {} 那么", "そうでなくもし {} なら"),
    ("else", "sinon", "sonst", "altrimenti", "иначе", "si no", "否则", "そうでなければ"),
    ("break loop", "quitter la boucle", "Schleife verlassen", "esci dal ciclo", "прервать цикл", "salir del bucle", "跳出循环", "ループを抜ける"),
    ("next iteration", "itération suivante", "nächster Durchlauf", "iterazione successiva", "следующая итерация", "siguiente iteración", "下一次循环", "次の繰り返しへ"),
    ("wait {} seconds", "attendre {} secondes", "warte {} Sekunden", "aspetta {} secondi", "ждать {} сек.", "esperar {} segundos", "等待 {} 秒", "{} 秒待つ"),
    ("# {}", "# {}", "# {}", "# {}", "# {}", "# {}", "# {}", "# {}"),
    ("print {}", "afficher {}", "ausgeben {}", "stampa {}", "вывести {}", "mostrar {}", "打印 {}", "{} を表示"),
    ("print {} without newline", "afficher {} sans retour à la ligne", "{} ohne Zeilenumbruch ausgeben", "stampa {} senza andare a capo",
     "вывести {} без перевода строки", "mostrar {} sin salto de línea", "打印 {}（不换行）", "{} を改行せずに表示"),
    ("ask {}", "demander {}", "frage {}", "chiedi {}", "спросить {}", "preguntar {}", "询问 {}", "{} と尋ねる"),
    ("ask for a number {}", "demander un nombre {}", "frage nach einer Zahl {}", "chiedi un numero {}", "спросить число {}",
     "preguntar un número {}", "询问一个数字 {}", "数を尋ねる {}"),
    ("set {} to {}", "mettre {} à {}", "setze {} auf {}", "imposta {} a {}", "присвоить {} значение {}", "poner {} a {}", "将 {} 设为 {}", "{} を {} にする"),
    ("add {} to {}", "ajouter {} à {}", "addiere {} zu {}", "aggiungi {} a {}", "добавить {} к {}", "sumar {} a {}", "将 {} 加到 {}", "{} を {} に加える"),
    ("variable {}", "variable {}", "Variable {}", "variabile {}", "переменная {}", "variable {}", "变量 {}", "変数 {}"),
    ("create list {} with {}", "créer la liste {} avec {}", "erstelle Liste {} mit {}", "crea lista {} con {}", "создать список {} из {}",
     "crear lista {} con {}", "创建列表 {}，内容 {}", "リスト {} を {} で作る"),
    ("append {} to list {}", "ajouter {} à la liste {}", "hänge {} an Liste {} an", "aggiungi {} alla lista {}", "добавить {} в список {}",
     "añadir {} a la lista {}", "将 {} 追加到列表 {}", "{} をリスト {} の末尾に追加"),
    ("set item {} of {} to {}", "mettre l'élément {} de {} à {}", "setze Element {} von {} auf {}", "imposta l'elemento {} di {} a {}",
     "присвоить элементу {} списка {} значение {}", "poner el elemento {} de {} a {}", "将第 {} 项（列表 {}）设为 {}", "{} 番目（リスト {}）を {} にする"),
    ("item {} of {}", "élément {} de {}", "Element {} von {}", "elemento {} di {}", "элемент {} из {}", "elemento {} de {}", "第 {} 项（列表 {}）", "{} 番目（リスト {}）"),
    ("length of {}", "longueur de {}", "Länge von {}", "lunghezza di {}", "длина {}", "longitud de {}", "{} 的长度", "{} の長さ"),
    ("{} modulo {}", "{} modulo {}", "{} modulo {}", "{} modulo {}", "{} по модулю {}", "{} módulo {}", "{} 除以 {} 的余数", "{} を {} で割った余り"),
    ("{} div {}", "{} div {}", "{} div {}", "{} div {}", "{} div {}", "{} div {}", "{} 整除 {}", "{} ÷ {}（整数）"),
    ("{} to the power of {}", "{} puissance {}", "{} hoch {}", "{} elevato a {}", "{} в степени {}", "{} elevado a {}", "{} 的 {} 次方", "{} の {} 乗"),
    ("random integer from {} to {}", "entier aléatoire de {} à {}", "Zufallszahl von {} bis {}", "intero casuale da {} a {}",
     "случайное целое от {} до {}", "entero aleatorio de {} a {}", "从 {} 到 {} 的随机整数", "{} から {} までの乱数"),
    ("round {}", "arrondir {}", "runde {}", "arrotonda {}", "округлить {}", "redondear {}", "四舍五入 {}", "{} を丸める"),
    ("square root of {}", "racine carrée de {}", "Quadratwurzel von {}", "radice quadrata di {}", "квадратный корень из {}",
     "raíz cuadrada de {}", "{} 的平方根", "{} の平方根"),
    ("absolute value of {}", "valeur absolue de {}", "Betrag von {}", "valore assoluto di {}", "модуль {}", "valor absoluto de {}", "{} 的绝对值", "{} の絶対値"),
    ("join {} {}", "assembler {} {}", "verbinde {} {}", "unisci {} {}", "соединить {} {}", "unir {} {}", "连接 {} {}", "{} と {} を結合"),
    ("string of {}", "texte de {}", "Text von {}", "stringa di {}", "строка из {}", "texto de {}", "{} 转为文本", "{} を文字列に"),
    ("integer of {}", "entier de {}", "Ganzzahl von {}", "intero di {}", "целое из {}", "entero de {}", "{} 转为整数", "{} を整数に"),
    ("float of {}", "décimal de {}", "Kommazahl von {}", "decimale di {}", "дробное из {}", "decimal de {}", "{} 转为小数", "{} を小数に"),
    ("{} and {}", "{} et {}", "{} und {}", "{} e {}", "{} и {}", "{} y {}", "{} 并且 {}", "{} かつ {}"),
    ("{} or {}", "{} ou {}", "{} oder {}", "{} o {}", "{} или {}", "{} o {}", "{} 或者 {}", "{} または {}"),
    ("not {}", "non {}", "nicht {}", "non {}", "не {}", "no {}", "非 {}", "{} ではない"),
    ("{} in {}", "{} dans {}", "{} in {}", "{} in {}", "{} в {}", "{} en {}", "{} 在 {} 中", "{} が {} に含まれる"),
    ("define {} ({})", "définir {} ({})", "definiere {} ({})", "definisci {} ({})", "определить {} ({})", "definir {} ({})", "定义 {} ({})", "{} ({}) を定義"),
    ("call {} ({})", "appeler {} ({})", "rufe {} ({}) auf", "chiama {} ({})", "вызвать {} ({})", "llamar a {} ({})", "调用 {} ({})", "{} ({}) を呼ぶ"),
    ("result of {} ({})", "résultat de {} ({})", "Ergebnis von {} ({})", "risultato di {} ({})", "результат {} ({})", "resultado de {} ({})", "{} ({}) 的结果", "{} ({}) の結果"),
    ("return {}", "retourner {}", "gib {} zurück", "restituisci {}", "вернуть {}", "devolver {}", "返回 {}", "{} を返す"),
    ("Python line {}", "ligne Python {}", "Python-Zeile {}", "riga Python {}", "строка Python {}", "línea de Python {}", "Python 行 {}", "Python 行 {}"),
    ("Python block {}", "bloc Python {}", "Python-Block {}", "blocco Python {}", "блок Python {}", "bloque de Python {}", "Python 块 {}", "Python ブロック {}"),
    ("Python expression {}", "expression Python {}", "Python-Ausdruck {}", "espressione Python {}", "выражение Python {}", "expresión de Python {}", "Python 表达式 {}", "Python 式 {}"),
]


_LANGUAGE_NOTICE = {}
_LANGUAGE_NOTICE.update({c: I18N_ROWS[[r[0] for r in I18N_ROWS].index(
    "Language changed. Restart ScratchPy to apply it.")][i] for i, (c, _) in enumerate(LANGUAGES) if i})
_LANGUAGE_NOTICE["en"] = "Language changed. Restart ScratchPy to apply it."


def set_language(code):
    """Select the interface language (call before building the window)."""
    global LANG
    codes = [c for c, _ in LANGUAGES]
    LANG = code if code in codes else "en"
    _I18N.clear()
    _I18N_PATTERNS.clear()
    if LANG == "en":
        return
    col = codes.index(LANG)
    for row in I18N_ROWS + I18N_BLOCKS:
        _I18N[row[0]] = row[col]
    for key, value in _I18N.items():
        if "%s" in key or "%d" in key:
            pat = re.escape(key).replace("%s", "(.*?)").replace("%d", "(\\d+)")
            _I18N_PATTERNS.append((re.compile(pat, re.S), value))


def tr(text):
    """Translate a user-interface string (strings with %s / %d placeholders also work once formatted)."""
    if LANG == "en" or not isinstance(text, str) or not text:
        return text
    hit = _I18N.get(text)
    if hit is not None:
        return hit
    for rx, value in _I18N_PATTERNS:
        m = rx.fullmatch(text)
        if m:
            groups = iter(tr(g) for g in m.groups())
            return re.sub(r"%[sd]", lambda _: next(groups), value)
    return text


def apply_block_language():
    """Show the block labels in the selected language (the generated Python is never affected)."""
    for sp in SPECS.values():
        text = sp.get("text")
        if not text:
            continue
        items, n = _items(tr(text) if LANG != "en" else text)
        if n == sp["nfields"]:
            sp["items"] = items
        sp["tlabel"] = " ".join(v for k, v in items if k == "t")


def install_i18n():
    """Translate every widget, menu entry, title and message box created from now on."""
    if LANG == "en":
        return
    orig_init = tk.BaseWidget.__init__

    def init(self, master, widgetName, cnf={}, kw={}, extra=()):
        for d in (cnf, kw):
            if isinstance(d, dict) and isinstance(d.get("text"), str):
                d["text"] = tr(d["text"])
        orig_init(self, master, widgetName, cnf, kw, extra)
    tk.BaseWidget.__init__ = init

    orig_conf = tk.Misc.configure

    def configure(self, cnf=None, **kw):
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        if isinstance(cnf, dict) and isinstance(cnf.get("text"), str):
            cnf = dict(cnf, text=tr(cnf["text"]))
        return orig_conf(self, cnf, **kw)
    tk.Misc.configure = tk.Misc.config = configure

    orig_add = tk.Menu.add

    def add(self, itemType, cnf={}, **kw):
        if isinstance(cnf, dict) and isinstance(cnf.get("label"), str):     # add_command passes a dict.
            cnf = dict(cnf, label=tr(cnf["label"]))
        if isinstance(kw.get("label"), str):
            kw["label"] = tr(kw["label"])
        return orig_add(self, itemType, cnf, **kw)
    tk.Menu.add = add

    orig_nb_add = ttk.Notebook.add

    def nb_add(self, child, **kw):
        if isinstance(kw.get("text"), str):
            kw["text"] = tr(kw["text"])
        return orig_nb_add(self, child, **kw)
    ttk.Notebook.add = nb_add

    orig_title = tk.Wm.wm_title

    def title(self, string=None):
        return orig_title(self, tr(string) if isinstance(string, str) else string)
    tk.Wm.wm_title = tk.Wm.title = title

    orig_set = tk.StringVar.set

    def var_set(self, value):
        return orig_set(self, tr(value) if isinstance(value, str) else value)
    tk.StringVar.set = var_set

    for name in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel",
                 "askretrycancel", "askyesnocancel", "askquestion"):
        fn = getattr(messagebox, name, None)
        if fn is None:
            continue

        def wrapper(*a, _fn=fn, **kw):
            a = [tr(x) if isinstance(x, str) else x for x in a]
            for k in ("title", "message"):
                if isinstance(kw.get(k), str):
                    kw[k] = tr(kw[k])
            return _fn(*a, **kw)
        setattr(messagebox, name, wrapper)


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


_COMMENTS = {}          # line number -> text of the full-line comments of the code being converted
_PLACEHOLDER_COMMENT = "(no blocks yet)"


def _collect_comments(src):
    """Full-line comments of `src` (comments after code on the same line are not blocks)."""
    found = {}
    try:
        import io
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and tok.line.strip().startswith("#"):
                text = tok.string[1:].strip()
                if text and text != _PLACEHOLDER_COMMENT:
                    found[tok.start[0]] = text
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return found


def _comment_blocks(before_line=None):
    """Comment blocks for the pending comments above `before_line` (all of them when None)."""
    done = [ln for ln in sorted(_COMMENTS) if before_line is None or ln < before_line]
    return [Block("comment", [_COMMENTS.pop(ln)]) for ln in done]


def _body(stmts):
    out = []
    for n in stmts:
        out.extend(_comment_blocks(getattr(n, "lineno", None)))
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
        return [B("change", [_u(n.value), n.target.id])]
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
    tree = ast.parse(src)
    _COMMENTS.clear()
    _COMMENTS.update(_collect_comments(src))
    try:
        return _body(tree.body) + _comment_blocks()
    finally:
        _COMMENTS.clear()


_HEADER = [("sys", None), ("time", None), ("random", None), ("math", None)]


def python_to_project(src, generated=False):
    """Like python_to_blocks, but top-level imports are not converted to blocks.
    Return (blocks, [(module, import_line), ...], paths).
    With generated=True, ignore the editor's standard import header and read
    sys.path.insert(0, '...') lines as project paths."""
    imports, paths, rest = [], [], []
    tree = ast.parse(src)
    for n in tree.body:
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
    _COMMENTS.clear()
    _COMMENTS.update(_collect_comments(src))
    try:
        return _body(rest) + _comment_blocks(), imports, paths
    finally:
        _COMMENTS.clear()


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


def _vec(pts, r0=5.0):
    """Control points of a closed vector outline with rounded corners.

    Each corner becomes three control points (start of the curve, the corner itself, end of the
    curve); the canvas draws them as true Bezier curves (smooth=True), so the curves stay smooth
    at every zoom level."""
    n, out = len(pts), []
    for i in range(n):
        (px, py), (x, y), (nx, ny) = pts[i - 1][:2], pts[i][:2], pts[(i + 1) % n][:2]
        r = pts[i][2] if len(pts[i]) > 2 else r0          # A vertex may carry its own radius.
        l1, l2 = math.hypot(px - x, py - y), math.hypot(nx - x, ny - y)
        if l1 < 1e-6 or l2 < 1e-6:
            out += [x, y]
            continue
        d1, d2 = min(2 * r, l1), min(2 * r, l2)     # The curve starts halfway to these points.
        out += [x + (px - x) / l1 * d1, y + (py - y) / l1 * d1, x, y,
                x + (nx - x) / l2 * d2, y + (ny - y) / l2 * d2]
    return out


def _hat_pts(x, y, hat=12, a=40, steps=30):
    """Dome of the 'when clicked' block, like in Scratch: an arc of an ellipse that starts on the
    left edge (below the top edge of the body), rises to a peak `hat` px above the body and comes
    back down onto the flat top edge at an angle. y + hat is the top edge of the body."""
    top = y + hat
    b = hat / 0.6                       # vertical radius
    d = b - hat                         # the arc starts d px below the top edge of the body
    cx, cy = x + a, top + d
    end = math.asin(d / b)
    pts = []
    for k in range(steps + 1):
        th = math.pi + (end - math.pi) * k / steps
        pts.append((cx + a * math.cos(th), cy - b * math.sin(th), 0))
    return pts


def _notch_r(x0, y, x1):      # Top edge (inward notch), from left to right.
    return [(x0 + 14, y, 2), (x0 + 18, y + 4, 2), (x0 + 30, y + 4, 2), (x0 + 34, y, 2), (x1, y)]


def _bump_l(x0, y):           # Bottom edge (outward tab), from right to left.
    return [(x0 + 34, y, 2), (x0 + 30, y + 4, 2), (x0 + 18, y + 4, 2), (x0 + 14, y, 2), (x0, y)]


def _spline(ctrl, steps=8):
    """Points of the closed quadratic Bezier outline the canvas draws for smooth=True."""
    pts = list(zip(ctrl[::2], ctrl[1::2]))
    if len(pts) > 1 and pts[0] == pts[-1]:      # Some Tk versions return the closing point too.
        pts.pop()
    n, out = len(pts), []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        m0 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        m1 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        for k in range(steps):
            t = k / steps
            u = 1 - t
            out.append((u * u * m0[0] + 2 * u * t * p1[0] + t * t * m1[0],
                        u * u * m0[1] + 2 * u * t * p1[1] + t * t * m1[1]))
    return out


def aa_image(ctrl, fill, outline, width, ss=3):
    """Anti-aliased picture of a block outline: drawn `ss` times larger, then reduced.
    Returns (image, x_offset, y_offset, key); the key lets identical shapes share one picture."""
    pts = _spline(ctrl)
    pad = int(width) + 2
    ox = int(math.floor(min(x for x, y in pts))) - pad
    oy = int(math.floor(min(y for x, y in pts))) - pad
    rel = [(round((x - ox) * 4) / 4, round((y - oy) * 4) / 4) for x, y in pts]     # Quarter-pixel precision.
    w = int(math.ceil(max(x for x, y in rel))) + pad
    h = int(math.ceil(max(y for x, y in rel))) + pad
    key = (fill, outline, width, w, h, tuple(rel))
    return rel, w, h, ox, oy, key


def aa_render(rel, w, h, fill, outline, width, ss=3):
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    xy = [(x * ss, y * ss) for x, y in rel]
    d.polygon(xy, fill=fill)
    d.line(xy + [xy[0], xy[1]], fill=outline, width=max(1, int(round(width * ss))), joint="curve")
    return big.resize((w, h), getattr(Image, "Resampling", Image).LANCZOS)


class Renderer:
    GAP, PADX, ROWH, FH = 6, 10, 34, 22
    IND, EMPTY, FOOT, MID, HAT = 24, 22, 24, 28, 13

    def __init__(self, canvas, font, place_entry=None):
        self.c = canvas
        self.font = font
        self.place_entry = place_entry
        self.lh = font.metrics("linespace")
        self.force_ctx = None
        self.selected = set()
        self.found, self.found_current = set(), None      # Search results (highlighted outlines).
        self.reset()

    def reset(self):
        self.memo = {}
        self.hits = []      # (x, y, w, h, block, context)
        self.snaps = []     # (x, y, list, index, dragging)
        self.slots = []     # (x, y, w, h, parent, index, dragging)
        self.in_drag = False
        self.polys = []     # (canvas item, fill, outline, width) of every block outline drawn

    def poly(self, ctrl, fill, outline, width):
        """Draw a block outline as a vector curve (smoothed into an anti-aliased picture later)."""
        item = self.c.create_polygon(ctrl, smooth=True, splinesteps=12, fill=fill, outline=outline,
                                     width=width, joinstyle="round", tags="shape")
        self.polys.append((item, fill, outline, width))
        return item

    def _ol(self, b, dark):
        """Return a thick white outline for selected blocks."""
        if b.uid in self.selected:
            return "#FFFFFF", 3
        if b.uid == self.found_current:
            return "#FF6A00", 4
        if b.uid in self.found:
            return "#FFD60A", 3
        return dark, 1

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
            self.poly(_vec(list(zip(pts[::2], pts[1::2])), 6), col, ol, wd)
        else:
            r = min(h / 2, 14)
            self.poly(_vec([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], r), col, ol, wd)
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
                top = _hat_pts(x, y, hat, min(0.38 * W, 42)) + [(x + W, y + hat)]
            else:
                top = [(x, y)] + _notch_r(x, y, x + W)
            pts = top + [(x + W, y + Hh)] + _bump_l(x, y + Hh)
            self.poly(_vec(pts, 5), col, ol, wd)
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
        self.poly(_vec(pts, 5), col, ol, wd)
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


FROZEN_PYTHON = None          # In the installed .exe: the Python that built it (set at startup).
_PY_INFO = ("import sys, json, site; print(json.dumps({'version': list(sys.version_info[:2]), "
            "'base': sys.base_prefix, 'paths': sys.path + [site.getusersitepackages()]}))")


def setup_frozen_python():
    """Packaged .exe: make every module of the Python that built it importable (standard library,
    pip packages, compiled ones like numpy). Return that interpreter, or None when unavailable."""
    if not getattr(sys, "frozen", False):
        return None
    py = None
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "python.txt"),
                  encoding="utf-8") as f:
            py = f.read().strip()
    except OSError:
        pass
    if not py or not os.path.isfile(py):
        py = system_python()
    if not py:
        return None
    try:
        out = subprocess.run([py, "-c", _PY_INFO], capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        info = json.loads(out.stdout)
    except Exception:
        return None
    if tuple(info.get("version", ())) != tuple(sys.version_info[:2]):
        return None                                   # Different Python version: compiled modules would not load.
    for p in info.get("paths", []):
        if p and not p.lower().endswith(".zip") and os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)                        # Appended: the modules bundled in the .exe keep priority.
    base = info.get("base", "")
    for d in (base, os.path.join(base, "DLLs")):
        if hasattr(os, "add_dll_directory") and os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
    importlib.invalidate_caches()
    return py


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


# --------------------------------------------------------------------------
# Recent files, built-in examples and keyboard shortcuts
# --------------------------------------------------------------------------
RECENT_MAX = 10


def push_recent(items, path, limit=RECENT_MAX):
    """Return the recent-files list with `path` first, without duplicates, at most `limit` long."""
    path = os.path.abspath(path)
    key = os.path.normcase(path)
    rest = [p for p in items if isinstance(p, str) and os.path.normcase(os.path.abspath(p)) != key]
    return ([path] + rest)[:limit]


EXAMPLES = {
    "Sum and comparison": """total = 0
for i in range(1, 6):
    total += i
    print("Partial sum: " + str(total))
if total > 10:
    print("It is greater than 10!")
elif total == 10:
    print("Exactly 10.")
else:
    print("It is less than 10.")
""",
    "Guess the number": """import random
secret = random.randint(1, 100)
tries = 0
guess = 0
print("I am thinking of a number between 1 and 100.")
while guess != secret:
    guess = int(input("Your guess? "))
    tries += 1
    if guess < secret:
        print("Higher!")
    elif guess > secret:
        print("Lower!")
print("Found in " + str(tries) + " tries!")
""",
    "Calculator": """a = float(input("First number? "))
op = input("Operation (+ - * /)? ")
b = float(input("Second number? "))
if op == "+":
    print(a + b)
elif op == "-":
    print(a - b)
elif op == "*":
    print(a * b)
elif op == "/":
    if b == 0:
        print("Cannot divide by zero.")
    else:
        print(a / b)
else:
    print("Unknown operation.")
""",
    "Multiplication table": """n = int(input("Which table? "))
for i in range(1, 11):
    print(str(n) + " x " + str(i) + " = " + str(n * i))
""",
    "FizzBuzz": """for i in range(1, 31):
    if i % 15 == 0:
        print("FizzBuzz")
    elif i % 3 == 0:
        print("Fizz")
    elif i % 5 == 0:
        print("Buzz")
    else:
        print(i)
""",
    "Greeting function": """def greet(name):
    print("Hello " + name)


name = input("Your name? ")
greet(name)
""",
}

# (id, label, default Tk sequence)
SHORTCUT_ACTIONS = [
    ("run", "Run the program", "<F5>"),
    ("stop", "Stop the program", "<Shift-F5>"),
    ("new", "New project", "<Control-n>"),
    ("open", "Open a file", "<Control-o>"),
    ("save", "Save the project", "<Control-s>"),
    ("find", "Search the workspace", "<Control-f>"),
    ("find_next", "Next search result", "<F3>"),
    ("find_prev", "Previous search result", "<Shift-F3>"),
    ("shortcuts", "Show the shortcuts", "<F1>"),
]
# Fixed shortcuts, listed in the help window only.
FIXED_SHORTCUTS = [
    ("Ctrl+Z / Ctrl+Y", "Undo / redo"),
    ("Ctrl+A", "Select all blocks"),
    ("Ctrl+C / Ctrl+V", "Copy / paste the selected blocks"),
    ("Ctrl+D", "Duplicate the selected blocks"),
    ("Delete", "Delete the selected blocks"),
    ("Ctrl+wheel, Ctrl+ +/-/0", "Zoom"),
]
_MODIFIER_KEYS = {"Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R",
                  "Super_L", "Super_R", "Caps_Lock", "Num_Lock", "ISO_Level3_Shift"}


def seq_label(seq):
    """'<Control-Shift-o>' -> 'Ctrl+Shift+O'."""
    parts = seq.strip("<>").split("-")
    key = parts[-1] if parts[-1] else "-"
    if seq.endswith("--"):
        parts, key = seq.strip("<>")[:-2].split("-") if seq.strip("<>")[:-2] else [], "-"
        parts = [x for x in parts if x]
    else:
        parts = parts[:-1]
    names = {"Control": "Ctrl", "Command": "Cmd", "minus": "-", "plus": "+", "equal": "="}
    out = [names.get(x, x) for x in parts]
    out.append(names.get(key, key.upper() if len(key) == 1 else key))
    return "+".join(out)


def event_to_seq(event):
    """Turn a key event into a Tk sequence, or None for a lone modifier key."""
    if event.keysym in _MODIFIER_KEYS:
        return None
    state = event.state
    mods = []
    if state & 0x4:
        mods.append("Control")
    if state & (0x20000 if sys.platform == "win32" else 0x8):
        mods.append("Alt")
    if state & 0x1:
        mods.append("Shift")
    key = event.keysym
    if len(key) == 1:
        key = key.lower()
    return "<%s>" % "-".join(mods + [key])


def shortcut_conflicts(mapping, action, seq):
    """Ids of the other actions that already use `seq`."""
    return [a for a, q in mapping.items() if a != action and q.lower() == seq.lower()]


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
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.job = None
        self.window = None
        self.message = None
        widget.bind("<Enter>", self.on_enter, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def on_enter(self, event):
        self.move(self.text, event.x_root + 12, event.y_root + 16)

    def move(self, message, x, y):
        if message == self.message:
            if self.window:
                self.window.geometry("+%d+%d" % (x, y))
            return
        self.hide()
        self.message = message
        self.job = self.widget.after(450, lambda: self.show(message, x, y))

    def show(self, message, x, y):
        self.job = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry("+%d+%d" % (x, y))
        tk.Label(self.window, text=message, justify="left", bg="#20242b", fg="white",
                 padx=7, pady=4, bd=1, relief="solid").pack()

    def hide(self, event=None):
        if self.job is not None:
            try:
                self.widget.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None
        if self.window is not None:
            try:
                self.window.destroy()
            except tk.TclError:
                pass
            self.window = None
        self.message = None


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
        saved_path = self.cfg.get("project_path")
        self.project_path = saved_path if isinstance(saved_path, str) else None
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
        self.found, self.found_current = [], None
        self.aa_ws, self.aa_pal = {}, {}      # Cached smooth block pictures.
        self.scripts = []
        self.saved_state = None
        self.undo_stack = []
        self.redo_stack = []
        self.undo_limit = 100
        self._edit_undo_before = None
        self._code_undo_before = None
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
        self.update_installer_payload = None
        self.update_checking = False
        self.closing = False
        self.cat = "Control"
        self._job = None
        self.build_ui()
        self.show_palette(self.cat)
        self.set_scripts([])          # Start with an empty workspace.
        self.mark_saved()
        self.autosaved_state = self.project_state()
        self.update_autosave_status()
        
        # Position the split panes after the window is drawn.
        root.after(800, self._init_paned_positions)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(40, self.poll)
        root.after(100, self.ai_poll)
        root.after(1500, self.check_for_updates)
        root.after(1000, self.restore_autosave)
        self.autosave_job = root.after(self.autosave_interval, self.autosave_tick)

    def check_for_updates(self, manual=False):
        if sys.platform != "win32":
            if manual:
                messagebox.showinfo("Updates", "Update checks are available on Windows only.",
                                    parent=self.root)
            return
        if getattr(sys, "frozen", False) and self.installed_updater() is None:
            if manual:
                messagebox.showinfo("Updates", "Updates are not supported by this packaged build.",
                                    parent=self.root)
            return
        if self.update_checking:
            if manual:
                messagebox.showinfo("Updates", "An update check is already in progress.",
                                    parent=self.root)
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
                if remote_key is None:
                    raise ValueError("GitHub did not return a valid version number.")
                if current_key is None:
                    raise ValueError("This copy does not have a valid version number.")
                if remote_key <= current_key:
                    if manual:
                        self.update_q.put_nowait(("current", None, None, remote_version, None))
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
                installer_payload = None
                try:
                    req = urllib.request.Request(
                        INSTALLER_URL, headers={"User-Agent": "ScratchPy updater"})
                    with urllib.request.urlopen(req, timeout=8) as response:
                        installer_payload = response.read(1024 * 1024 + 1)
                    if len(installer_payload) > 1024 * 1024:
                        installer_payload = None
                    else:
                        compile(installer_payload.decode("utf-8-sig"),
                                "install_scratchpy.py", "exec")
                except Exception:
                    installer_payload = None
                self.update_q.put_nowait(("update", payload, installer_payload,
                                          remote_version, None))
            except Exception as ex:
                if manual:
                    try:
                        self.update_q.put_nowait(("error", None, None, None, str(ex)))
                    except queue.Full:
                        pass
            finally:
                self.update_checking = False

        threading.Thread(target=check, daemon=True).start()
        self.root.after(200, self.poll_update)

    def poll_update(self):
        if self.closing:
            return
        try:
            status, payload, installer_payload, remote_version, error = self.update_q.get_nowait()
        except queue.Empty:
            if self.update_checking:
                self.root.after(200, self.poll_update)
            return
        if status == "current":
            messagebox.showinfo("Updates", "ScratchPy %s is up to date." % APP_VERSION,
                                parent=self.root)
            return
        if status == "error":
            messagebox.showerror("Updates", "Could not check for updates:\n%s" % error,
                                 parent=self.root)
            return
        if messagebox.askyesno(
                "Update available",
                "ScratchPy %s is available. You are using %s. Install the update now?" %
                (remote_version, APP_VERSION), parent=self.root):
            self.update_payload = payload
            self.update_installer_payload = installer_payload
            self.on_close()

    def show_about(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("About ScratchPy")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="ScratchPy", font=self.font).pack(anchor="w")
        ttk.Label(body, text="Version %s" % APP_VERSION).pack(anchor="w", pady=(4, 14))
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Check for updates",
                   command=lambda: self.check_for_updates(manual=True)).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="GitHub",
                   command=lambda: webbrowser.open("https://github.com/redcat67400-rgb/ScratchPy")).pack(
                       side="left", padx=(0, 6))
        ttk.Button(actions, text="Close", command=dialog.destroy).pack(side="right")
        ToolTip(actions.winfo_children()[0], "Check GitHub for a newer ScratchPy version")
        ToolTip(actions.winfo_children()[1], "Open the ScratchPy GitHub repository")
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry("+%d+%d" % (max(0, x), max(0, y)))

    def installed_updater(self):
        """(folder, installer, python) when this .exe was installed by install_scratchpy.py."""
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data or not getattr(sys, "frozen", False):
            return None
        folder = os.path.abspath(os.path.join(local_app_data, "ScratchPy"))
        if os.path.normcase(os.path.dirname(os.path.abspath(sys.executable))) != os.path.normcase(folder):
            return None
        installer = os.path.join(folder, "install_scratchpy.py")
        try:
            with open(os.path.join(folder, "python.txt"), encoding="utf-8") as f:
                python = f.read().strip()
        except OSError:
            return None
        if not (os.path.isfile(installer) and os.path.isfile(python)):
            return None
        return folder, installer, python

    def install_update(self):
        if self.update_payload is None:
            return True
        if getattr(sys, "frozen", False):                  # Installed .exe: the installer rebuilds it.
            info = self.installed_updater()
            if info is None:
                return True
            folder, installer, python = info
            try:
                subprocess.Popen(
                    [python, installer, "--update", "--wait-pid", str(os.getpid()), "--restart"],
                    cwd=folder, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=(getattr(subprocess, "DETACHED_PROCESS", 0) |
                                   getattr(subprocess, "CREATE_NO_WINDOW", 0)))
                return True
            except OSError as ex:
                messagebox.showerror("Update", "Could not start the installed updater:\n%s" % ex,
                                     parent=self.root)
                return False
        local_app_data = os.environ.get("LOCALAPPDATA")
        installer_payload = self.update_installer_payload
        if local_app_data:
            installed_folder = os.path.normcase(os.path.abspath(
                os.path.join(local_app_data, "ScratchPy")))
            current_folder = os.path.normcase(os.path.abspath(os.path.dirname(__file__)))
            installer = os.path.join(installed_folder, "install_scratchpy.py")
            if current_folder == installed_folder and os.path.isfile(installer):
                try:
                    subprocess.Popen(
                        [sys.executable, installer, "--update", "--wait-pid",
                         str(os.getpid()), "--restart"],
                        cwd=installed_folder, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=(getattr(subprocess, "DETACHED_PROCESS", 0) |
                                       getattr(subprocess, "CREATE_NO_WINDOW", 0)))
                    return True
                except OSError as ex:
                    messagebox.showerror(
                        "Update", "Could not start the installed updater:\n%s" % ex,
                        parent=self.root)
                    return False
        folder = None
        try:
            target = os.path.abspath(__file__)
            folder = tempfile.mkdtemp(prefix="scratchpy-update-")
            staged = os.path.join(folder, "scratchpy.pyw")
            staged_installer = (os.path.join(folder, "install_scratchpy.py")
                                if installer_payload else None)
            updater = os.path.join(folder, "update.ps1")
            with open(staged, "wb") as f:
                f.write(self.update_payload)
            if staged_installer:
                with open(staged_installer, "wb") as f:
                    f.write(installer_payload)

            def ps_quote(value):
                return "'" + value.replace("'", "''") + "'"

            copy_installer = (
                "Copy-Item -LiteralPath %s -Destination %s -Force\n" %
                (ps_quote(staged_installer),
                 ps_quote(os.path.join(os.path.dirname(target), "install_scratchpy.py")))
            ) if staged_installer else ""
            script = (
                "$processId = %d\n"
                "while (Get-Process -Id $processId -ErrorAction SilentlyContinue) { "
                "Start-Sleep -Seconds 1 }\n"
                "Copy-Item -LiteralPath %s -Destination %s -Force\n"
                "%s"
                "if ($?) { Start-Process -FilePath %s "
                "-ArgumentList ('\"' + %s + '\"') }\n"
                "Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force\n"
                "Remove-Item -LiteralPath %s -Recurse -Force\n"
            ) % (os.getpid(), ps_quote(staged), ps_quote(target), copy_installer,
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

    # ---------- search in the workspace (Ctrl+F) ----------
    def build_find_bar(self, parent):
        bar = tk.Frame(parent, bd=1, relief="solid")
        self.find_var = tk.StringVar()
        self.find_count = tk.StringVar(value="")
        tk.Label(bar, text="Find:").pack(side="left", padx=(6, 2))
        self.find_entry = ttk.Entry(bar, textvariable=self.find_var, width=24)
        self.find_entry.pack(side="left", pady=4)
        tk.Label(bar, textvariable=self.find_count, width=9).pack(side="left", padx=4)
        for text, step, tip in (("▲", -1, "Previous result (Shift+F3)"), ("▼", 1, "Next result (F3 / Enter)")):
            b = ttk.Button(bar, text=text, width=2, style="Panel.TButton",
                           command=lambda st=step: self.find_step(st))
            b.pack(side="left", padx=1)
            ToolTip(b, tip)
        close = ttk.Button(bar, text="✕", width=2, style="Panel.TButton", command=self.hide_find)
        close.pack(side="left", padx=(1, 4))
        ToolTip(close, "Close search (Esc)")
        self.find_bar = bar
        self.find_var.trace_add("write", lambda *a: self.run_find())
        self.find_entry.bind("<Return>", lambda e: (self.find_step(1), "break")[1])
        self.find_entry.bind("<Shift-Return>", lambda e: (self.find_step(-1), "break")[1])
        self.find_entry.bind("<Escape>", lambda e: (self.hide_find(), "break")[1])

    def show_find(self):
        self.tabs.select(self.main_paned)
        self.find_bar.place(relx=1.0, x=-24, y=8, anchor="ne")
        self.find_bar.lift()
        self.find_entry.focus_set()
        self.find_entry.selection_range(0, "end")
        self.run_find()

    def hide_find(self):
        self.find_bar.place_forget()
        self.found, self.found_current = [], None
        self.render()
        self.ws.focus_set()

    def run_find(self):
        """Search again (the text changed or the blocks did) and jump to the first result."""
        self.found = find_blocks([b for b, ctx, anc in self.iter_blocks()], self.find_var.get())
        self.found_current = self.found[0] if self.found else None
        self.update_find_count()
        self.render()
        self.scroll_to_block(self.found_current)

    def find_step(self, step):
        if not self.find_bar.winfo_ismapped():
            return self.show_find()
        self.found = find_blocks([b for b, ctx, anc in self.iter_blocks()], self.find_var.get())
        if not self.found:
            self.found_current = None
        else:
            i = self.found.index(self.found_current) if self.found_current in self.found else -step
            self.found_current = self.found[(i + step) % len(self.found)]
        self.update_find_count()
        self.render()
        self.scroll_to_block(self.found_current)

    def update_find_count(self):
        if not self.find_var.get().strip():
            self.find_count.set("")
        elif not self.found:
            self.find_count.set("No result")
        else:
            self.find_count.set("%d / %d" % (self.found.index(self.found_current) + 1, len(self.found)))

    def scroll_to_block(self, uid):
        """Scroll the workspace so that the block is visible (roughly a third from the top)."""
        if uid is None:
            return
        hit = next((h for h in self.wsr.hits if h[4].uid == uid), None)
        if hit is None:
            return
        c, z = self.ws, self.zoom
        try:
            _, _, sw, sh = (float(v) for v in str(c.cget("scrollregion")).split())
        except ValueError:
            return
        x, y = hit[0] * z, hit[1] * z
        if sh > 0:
            c.yview_moveto(max(0.0, (y - c.winfo_height() / 3) / sh))
        if sw > 0 and (x < c.canvasx(0) or x + hit[2] * z > c.canvasx(c.winfo_width())):
            c.xview_moveto(max(0.0, (x - 60) / sw))

    # ---------- right column: panels that can be moved and hidden ----------
    def add_panel_controls(self, head, key):
        """▲ ▼ ✕ buttons in the header of a panel (packed first = rightmost)."""
        if not hasattr(self, "panel_buttons"):
            self.panel_buttons = {}
        hide = ttk.Button(head, text="✕", width=2, style="Panel.TButton",
                          command=lambda: self.set_panel_visible(key, False))
        down = ttk.Button(head, text="▼", width=2, style="Panel.TButton",
                          command=lambda: self.move_panel(key, 1))
        up = ttk.Button(head, text="▲", width=2, style="Panel.TButton",
                        command=lambda: self.move_panel(key, -1))
        for b in (hide, down, up):
            b.pack(side="right", padx=1, pady=2)
        ToolTip(hide, "Hide this panel (Panels menu to show it again)")
        ToolTip(down, "Move this panel down")
        ToolTip(up, "Move this panel up")
        self.panel_buttons[key] = (up, down)

    def layout_right_panels(self, initial=False, reset_sizes=True):
        """(Re)build the right column from the saved order and visibility."""
        shown = [k for k in self.panel_order if k not in self.panel_hidden]
        for frame in self.panels.values():
            try:
                self.right_paned.forget(frame)
            except tk.TclError:
                pass
        for k in shown:
            self.right_paned.add(self.panels[k], minsize=RIGHT_PANELS[k][1])
        if shown and not self.right_shown:
            self.main_paned.add(self.right_paned, minsize=300)
            self.right_shown = True
        elif not shown and self.right_shown:
            self.main_paned.forget(self.right_paned)
            self.right_shown = False
        for k, var in getattr(self, "panel_vars", {}).items():      # Keep the Settings check boxes in sync.
            var.set(k in shown)
        for k, (up, down) in self.panel_buttons.items():
            up.configure(state="normal" if k in shown and k != shown[0] else "disabled")
            down.configure(state="normal" if k in shown and k != shown[-1] else "disabled")
        if reset_sizes and not initial:
            self.root.after_idle(self._place_right_sashes)
        if self.right_shown and not initial:
            self.root.after_idle(self._place_main_sashes)

    def _place_right_sashes(self):
        try:
            h = self.right_paned.winfo_height()
            if h > 200:
                for i, y in enumerate(panel_sash_positions(self.panel_order, self.panel_hidden, h)):
                    self.right_paned.sash_place(i, 0, y)
        except tk.TclError:
            pass

    def _place_main_sashes(self):
        try:
            w = self.main_paned.winfo_width()
            if w > 200 and len(self.main_paned.panes()) >= 3:
                self.main_paned.sash_place(0, int(w * 0.214), 0)
                self.main_paned.sash_place(1, w - int(w * 0.277), 0)
        except tk.TclError:
            pass

    def save_panel_layout(self):
        self.cfg["right_panels"] = {"order": self.panel_order, "hidden": self.panel_hidden}
        save_config(self.cfg)

    def move_panel(self, key, step):
        shown = [k for k in self.panel_order if k not in self.panel_hidden]
        if key not in shown:
            return
        i = shown.index(key) + step
        if not 0 <= i < len(shown):
            return
        other = shown[i]
        a, b = self.panel_order.index(key), self.panel_order.index(other)
        self.panel_order[a], self.panel_order[b] = self.panel_order[b], self.panel_order[a]
        self.save_panel_layout()
        self.layout_right_panels()

    def set_panel_visible(self, key, visible):
        if visible and key in self.panel_hidden:
            self.panel_hidden.remove(key)
        elif not visible and key not in self.panel_hidden:
            self.panel_hidden.append(key)
        else:
            return
        self.save_panel_layout()
        self.layout_right_panels()

    def reset_panel_layout(self):
        self.panel_order, self.panel_hidden = list(RIGHT_PANELS), []
        self.save_panel_layout()
        self.layout_right_panels()

    def show_panels_menu(self, anchor):
        menu = tk.Menu(self.root, tearoff=0)          # Built on demand so it always follows the theme.
        for k in self.panel_order:
            var = tk.BooleanVar(value=k not in self.panel_hidden)
            menu.add_checkbutton(label=RIGHT_PANELS[k][0], variable=var,
                                 command=lambda k=k, v=var: self.set_panel_visible(k, v.get()))
        menu.add_separator()
        mm = tk.BooleanVar(value=self.minimap_on)
        menu.add_checkbutton(label="Minimap", variable=mm, command=lambda: self.set_minimap(mm.get()))
        menu.add_command(label="Keyboard shortcuts…", command=self.show_shortcuts)
        menu.add_separator()
        menu.add_command(label="Reset layout", command=self.reset_panel_layout)
        menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

    def _init_paned_positions(self):
        """Default panel proportions (same layout whatever the screen size):
        palette 21 %, workspace 51 %, right column 28 %; right column: code 33 %, console 30 %, assistant 37 %."""
        try:
            w = self.main_paned.winfo_width()
            if w > 200:
                self.main_paned.sash_place(0, int(w * 0.214), 0)
                self.main_paned.sash_place(1, w - int(w * 0.277), 0)

            self._place_right_sashes()
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
        self.minimap_on = bool(self.cfg.get("minimap", True))
        if split_theme(self.theme_name) is None:
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
        dark = split_theme(self.theme_name)[1] == "dark"
        colors = theme_palette(self.theme_name)
        self.theme_colors = colors
        self.BG, self.BG2, self.EDIT = colors["BG"], colors["BG2"], colors["EDIT"]
        self.FG, self.MUTED = colors["FG"], colors["MUTED"]
        self.ACCENT, self.BORDER = colors["ACCENT"], colors["BORDER"]
        self.root.configure(bg=self.BG)
        self.style_titlebar(self.root)
        # Defaults for widgets created later (dialogs such as "Import a library", context menus,
        # drop-down lists): they must follow the current theme, not the one chosen at startup.
        for key, value in (("Background", self.BG), ("Foreground", self.FG),
                           ("highlightBackground", self.BG), ("highlightColor", self.ACCENT),
                           ("Menu.background", self.BG2), ("Menu.foreground", self.FG),
                           ("Menu.activeBackground", self.ACCENT), ("Menu.activeForeground", "white"),
                           ("Menu.relief", "flat"), ("Menu.borderWidth", 0),
                           ("PanedWindow.background", colors["SASH"]),
                           ("Entry.background", self.EDIT), ("Entry.foreground", self.FG),
                           ("Entry.insertBackground", self.FG),
                           ("Entry.selectBackground", colors["SELECT"]),
                           ("Entry.selectForeground", self.FG),
                           ("Text.background", self.EDIT), ("Text.foreground", self.FG),
                           ("Listbox.background", self.EDIT), ("Listbox.foreground", self.FG),
                           ("TCombobox*Listbox.background", self.EDIT),
                           ("TCombobox*Listbox.foreground", self.FG),
                           ("TCombobox*Listbox.selectBackground", self.ACCENT),
                           ("TCombobox*Listbox.selectForeground", "white")):
            self.root.option_add("*" + key, value, 80)       # 80 = "interactive": overrides startup defaults
        st = self.style
        st.configure(".", background=self.BG, foreground=self.FG,
                     fieldbackground=self.EDIT, bordercolor=self.BORDER,
                     lightcolor=self.BG2, darkcolor=self.BG2, troughcolor=self.BG,
                     focuscolor=self.BG, insertcolor=self.FG)
        st.configure("Panel.TButton", padding=(5, 1))          # Small ▲ ▼ ✕ buttons of the panels.
        st.configure("TButton", background=self.BG2, foreground=self.FG,
                   relief="solid", borderwidth=1, bordercolor=colors["BUTTON_BORDER"])
        st.map("TButton", background=[("pressed", self.BORDER), ("active", self.BG2)],
               foreground=[("disabled", self.MUTED)],
               bordercolor=[("active", self.ACCENT), ("pressed", self.ACCENT)])
        if dark:
            run_colors = ("#2e7d4f", "#37955d", "#276b43", "#58a879")
            stop_colors = ("#8f3b3b", "#a84646", "#7a3030", "#c06161")
            button_text = self.FG
        else:
            run_colors = ("#15803d", "#166534", "#14532d", "#166534")
            stop_colors = ("#dc2626", "#b91c1c", "#991b1b", "#b91c1c")
            button_text = "white"
        st.configure("Run.TButton", background=run_colors[0], foreground=button_text,
                     bordercolor=run_colors[3])
        st.map("Run.TButton", background=[("pressed", run_colors[2]),
                                           ("active", run_colors[1])],
               foreground=[("active", button_text), ("pressed", button_text)])
        st.configure("Stop.TButton", background=stop_colors[0], foreground=button_text,
                     bordercolor=stop_colors[3])
        st.map("Stop.TButton", background=[("pressed", stop_colors[2]),
                                            ("active", stop_colors[1])],
               foreground=[("active", button_text), ("pressed", button_text)])
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

        category_labels = set()
        for lb in getattr(self, "cat_labels", {}).values():     # Tabs keep their own colours.
            category_labels.update((lb, getattr(lb, "bar", lb)))

        def recolor(parent):
            for widget in parent.winfo_children():
                if widget in category_labels or getattr(widget, "keep_color", False):
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
                                selectbackground=colors["SELECT"])
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
        if split_theme(theme) is None or theme == self.theme_name:
            return
        self.theme_name = theme
        self.cfg["theme"] = theme
        save_config(self.cfg)
        if hasattr(self, "settings_mode_var"):
            self.settings_accent_var.set(split_theme(theme)[0])
            self.settings_mode_var.set(split_theme(theme)[1])
        self.apply_theme()

    # ---------- interface ----------
    def build_ui(self):
        root = self.root
        bar = tk.Frame(root, padx=8, pady=6)
        bar.pack(side="top", fill="x")
        tk.Frame(root, height=1, bg=self.BORDER).pack(side="top", fill="x")
        tips = {"▶ Run": "Run the current program", "■ Stop": "Stop the running program",
            "Undo": "Undo the last edit (Ctrl+Z)", "Redo": "Redo the last undone edit (Ctrl+Y)",
            "New": "Create a new project", "Open (.py or project)…": "Open Python or ScratchPy project",
            "Save": "Save the current project (Ctrl+S)", "Save As…": "Save to a new project file",
            "Export .py…": "Export the generated Python code", "Import a library…": "Add blocks from a Python library",
            "Recent ▾": "Reopen a recent file", "Examples ▾": "Load a built-in example program"}
        for item in (("▶ Run", self.run), ("■ Stop", self.stop), None,
              ("Undo", self.undo), ("Redo", self.redo), None,
                  ("New", self.new), ("Open (.py or project)…", self.open_file), ("Recent ▾", "recent"),
                  ("Save", self.save_file), ("Save As…", self.save_as),
                  ("Export .py…", self.export_py),
                  None, ("Import a library…", self.import_lib),
              ("Examples ▾", "examples"), None, ("About", self.show_about)):
            if item is None:
                ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)
                continue
            text, cmd = item
            holder = []
            if cmd == "recent":
                cmd = lambda h=holder: self.show_recent_menu(h[0])
            elif cmd == "examples":
                cmd = lambda h=holder: self.show_examples_menu(h[0])
            sty = "Run.TButton" if cmd == self.run else "Stop.TButton" if cmd == self.stop else "TButton"
            button = ttk.Button(bar, text=text, command=cmd, style=sty)
            holder.append(button)
            button.pack(side="left", padx=2)
            ToolTip(button, tips.get(text, "About ScratchPy"))
        zf = tk.Frame(bar)
        zf.pack(side="right")
        self.zoom_var = tk.StringVar(value="100 %")
        zoom_in = ttk.Button(zf, text="+", width=3, command=lambda: self.zoom_by(1.25))
        zoom_in.pack(side="right", padx=2)
        ToolTip(zoom_in, "Zoom in")
        zoom_reset = ttk.Button(zf, textvariable=self.zoom_var, width=6,
                                command=lambda: self.set_zoom(1.0))
        zoom_reset.pack(side="right")
        ToolTip(zoom_reset, "Reset zoom to 100%")
        zoom_out = ttk.Button(zf, text="−", width=3, command=lambda: self.zoom_by(0.8))
        zoom_out.pack(side="right", padx=2)
        ToolTip(zoom_out, "Zoom out")
        tk.Label(zf, text="Zoom:").pack(side="right", padx=(8, 2))
        panels_button = ttk.Button(bar, text="Panels ▾", command=lambda: self.show_panels_menu(panels_button))
        panels_button.pack(side="right", padx=10)
        ToolTip(panels_button, "Show, hide or reset the panels of the right column")

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
        self.ws.configure(yscrollcommand=lambda *a: (vs.set(*a), self.update_minimap()),
                          xscrollcommand=lambda *a: (hs.set(*a), self.update_minimap()))
        vs.pack(side="right", fill="y")
        hs.pack(side="bottom", fill="x")
        self.ws.pack(side="left", fill="both", expand=True)
        self.build_find_bar(mid)
        self.build_minimap(mid)
        self.main_paned.add(mid, minsize=300, stretch="always")

        # 3. Right panel (code + console + AI assistant)
        self.right_paned = tk.PanedWindow(self.main_paned, orient="vertical", sashwidth=6, sashrelief="flat",
                                     opaqueresize=False)
        
        # Python code.
        codef = tk.Frame(self.right_paned)
        head = tk.Frame(codef)
        head.pack(fill="x")
        tk.Label(head, text="Python code (editable)", font=self.font).pack(side="left", padx=4)
        self.add_panel_controls(head, "code")
        copy_code_button = ttk.Button(head, text="Copy", command=self.copy_code)
        copy_code_button.pack(side="right", padx=4, pady=2)
        ToolTip(copy_code_button, "Copy generated Python code")
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
        code_modifiers = ["Control"] + (["Command"] if sys.platform == "darwin" else [])
        for modifier in code_modifiers:
            self.code.bind("<%s-z>" % modifier, self.undo)
            self.code.bind("<%s-y>" % modifier, self.redo)
            self.code.bind("<%s-Shift-z>" % modifier, self.redo)
        self.code.bind("<Tab>", self.code_tab)
        self.code.bind("<Return>", self.code_return)
        for seq in ("<Shift-Tab>", "<ISO_Left_Tab>"):
            try:
                self.code.bind(seq, self.code_dedent)
            except tk.TclError:
                pass

        # Console
        conf = tk.Frame(self.right_paned)
        console_head = tk.Frame(conf)
        console_head.pack(fill="x")
        tk.Label(console_head, text="Console", font=self.font).pack(side="left", padx=4)
        self.add_panel_controls(console_head, "console")
        self.console_ai_btn = ttk.Button(console_head, text="Ask AI to fix", style="Panel.TButton",
                                         command=self.ai_fix_console)
        ToolTip(self.console_ai_btn, "Send the error to the AI assistant")
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
        send_button = ttk.Button(inp, text="Send", command=self.send_input)
        send_button.pack(side="left", padx=4)
        ToolTip(send_button, "Send input to the running program")

        # Gemini AI assistant.
        ai_frame = tk.Frame(self.right_paned)
        ai_top = tk.Frame(ai_frame)
        ai_top.pack(fill="x")
        tk.Label(ai_top, text="Gemini AI assistant", font=self.font).pack(side="left", padx=4)
        self.add_panel_controls(ai_top, "assistant")
        new_chat_button = ttk.Button(ai_top, text="New chat", command=self.ai_reset)
        new_chat_button.pack(side="right", padx=2)
        ToolTip(new_chat_button, "Clear the assistant conversation")
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
        quick = tk.Frame(ai_frame)
        quick.pack(side="bottom", fill="x")
        tk.Label(quick, text="Quick:").pack(side="left", padx=4)
        for kind, (label, _) in QUICK_PROMPTS.items():
            qb = ttk.Button(quick, text=label, style="Panel.TButton", command=lambda k=kind: self.ai_quick(k))
            qb.pack(side="left", padx=2, pady=2)
            ToolTip(qb, "%s the selected code (or the whole program if nothing is selected)" % label)
        tk.Label(ai_inp, text="Prompt:").pack(side="left", padx=4)
        self.ai_var = tk.StringVar()
        ai_ent = ttk.Entry(ai_inp, textvariable=self.ai_var)
        ai_ent.pack(side="left", fill="x", expand=True, padx=2)
        ai_ent.bind("<Return>", self.ask_gemini)
        self.ai_btn = ttk.Button(ai_inp, text="Ask", command=self.ask_gemini)
        self.ai_btn.pack(side="left", padx=4)
        ToolTip(self.ai_btn, "Send your question to the programming assistant")
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
        self.panels = {"code": codef, "console": conf, "assistant": ai_frame}
        self.panel_order, self.panel_hidden = clean_panel_layout(self.cfg.get("right_panels"))

        self.right_shown = False
        self.layout_right_panels(initial=True)

        self.tabs.add(self.main_paned, text="Workspace")
        self.settings_tab = ttk.Frame(self.tabs, padding=20)
        self.tabs.add(self.settings_tab, text="Settings")
        ttk.Label(self.settings_tab, text="Settings", font=self.font).pack(anchor="w", pady=(0, 16))
        appearance = ttk.LabelFrame(self.settings_tab, text="Appearance", padding=14)
        appearance.pack(anchor="nw", fill="x")
        ttk.Label(appearance, text="Theme").grid(row=0, column=0, sticky="w", padx=(0, 24))
        accent0, mode0 = split_theme(self.theme_name)
        self.settings_accent_var = tk.StringVar(value=accent0)
        self.settings_mode_var = tk.StringVar(value=mode0)

        def choose_theme():
            self.set_theme(join_theme(self.settings_accent_var.get(), self.settings_mode_var.get()))

        ttk.Radiobutton(appearance, text="Light", value="light", variable=self.settings_mode_var,
                        command=choose_theme).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Radiobutton(appearance, text="Dark", value="dark", variable=self.settings_mode_var,
                        command=choose_theme).grid(row=0, column=2, sticky="w", padx=6)
        ttk.Label(appearance, text="Colour").grid(row=1, column=0, sticky="w", padx=(0, 24), pady=(10, 0))
        colour_row = ttk.Frame(appearance)
        colour_row.grid(row=1, column=1, columnspan=6, sticky="w", pady=(10, 0))
        for accent in ACCENTS:
            cell = ttk.Frame(colour_row)
            cell.pack(side="left", padx=(0, 10))
            swatch = "#8a93a3" if accent == "default" else _hsl(ACCENTS[accent], .72, .55)
            sw = tk.Frame(cell, width=14, height=14, bg=swatch)
            sw.keep_color = True                    # The theme recolouring must not touch the swatches.
            sw.pack(side="left", padx=(0, 4))
            ttk.Radiobutton(cell, text=accent.capitalize(), value=accent, variable=self.settings_accent_var,
                            command=choose_theme).pack(side="left")
        language_box = ttk.LabelFrame(self.settings_tab, text="Language", padding=14)
        language_box.pack(anchor="nw", fill="x", pady=(12, 0))
        names = [n for _, n in LANGUAGES]
        self.language_var = tk.StringVar(value=dict(LANGUAGES).get(LANG, "English"))
        language_combo = ttk.Combobox(language_box, textvariable=self.language_var, values=names,
                                      state="readonly", width=18)
        language_combo.pack(side="left")
        language_combo.bind("<<ComboboxSelected>>", self.choose_language)
        panels_box = ttk.LabelFrame(self.settings_tab, text="Panels (right column)", padding=14)
        panels_box.pack(anchor="nw", fill="x", pady=(12, 0))
        self.panel_vars = {}
        for i, k in enumerate(RIGHT_PANELS):
            var = tk.BooleanVar(value=k not in self.panel_hidden)
            self.panel_vars[k] = var
            ttk.Checkbutton(panels_box, text=RIGHT_PANELS[k][0], variable=var,
                            command=lambda k=k: self.set_panel_visible(k, self.panel_vars[k].get())).grid(
                                row=0, column=i, sticky="w", padx=(0, 18))
        reset_button = ttk.Button(panels_box, text="Reset layout", command=self.reset_panel_layout)
        reset_button.grid(row=0, column=len(RIGHT_PANELS), sticky="w")
        ToolTip(reset_button, "Show all panels in their default order")
        autosave_box = ttk.LabelFrame(self.settings_tab, text="Automatic save", padding=14)
        autosave_box.pack(anchor="nw", fill="x", pady=(12, 0))
        ttk.Label(autosave_box, text="Backup file").grid(row=0, column=0, sticky="w", padx=(0, 18))
        ttk.Label(autosave_box, text=os.path.join("save", "autosave.json")).grid(
            row=0, column=1, sticky="w")
        self.autosave_status_var = tk.StringVar(value=tr("Waiting for changes"))
        ttk.Label(autosave_box, textvariable=self.autosave_status_var).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.palr = Renderer(self.pal, self.font)
        self.wsr = Renderer(self.ws, self.font, self.place_entry)

        for cv, src in ((self.pal, "pal"), (self.ws, "ws")):
            cv.bind("<ButtonPress-1>", lambda e, s=src: self.on_press(e, s))
            cv.bind("<B1-Motion>", self.on_motion)
            cv.bind("<ButtonRelease-1>", self.on_release)
        self.palette_tip = ToolTip(self.pal, "")
        self.pal.bind("<Motion>", self.on_palette_hover, add="+")
        self.pal.bind("<Leave>", self.palette_tip.hide, add="+")
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
            self.root.bind_all("<%s-z>" % m, self.undo, add="+")
            self.root.bind_all("<%s-y>" % m, self.redo, add="+")
            self.root.bind_all("<%s-Shift-z>" % m, self.redo, add="+")
        root.bind_all("<Control-MouseWheel>", self.on_zoom_wheel)
        root.bind_all("<Control-Button-4>", self.on_zoom_wheel)
        root.bind_all("<Control-Button-5>", self.on_zoom_wheel)
        for seq, f in (("<Control-minus>", 0.8), ("<Control-plus>", 1.25), ("<Control-equal>", 1.25)):
            root.bind_all(seq, lambda e, f=f: self.zoom_by(f))
        root.bind_all("<Control-Key-0>", lambda e: self.set_zoom(1.0))
        self.bound_shortcuts = []
        self.bind_shortcuts()
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
        for i, (name, (col, dark)) in enumerate(CATS.items()):
            cell = tk.Frame(self.catf, bg=self.catf.cget("bg"), cursor="hand2")
            cell.grid(row=i // 3, column=i % 3, sticky="nsew", padx=3, pady=3)
            lb = tk.Label(cell, text=name, bg=col, fg=text_on(col), font=self.font, padx=10, pady=6,
                          cursor="hand2", bd=0, anchor="center")
            lb.pack(fill="both", expand=True)
            bar = tk.Frame(cell, height=4, bg=dark)         # Coloured base line; white when selected.
            bar.pack(fill="x")
            lb.bar, lb.base, lb.dark = bar, col, dark
            for w in (cell, lb, bar):
                w.bind("<Button-1>", lambda e, n=name: self.show_palette(n))
            lb.bind("<Enter>", lambda e, l=lb: l.configure(bg=_lighten(l.base)))
            lb.bind("<Leave>", lambda e, l=lb: l.configure(bg=l.base))
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
                if q in SPECS[t]["label"].lower() or q in t.lower()
                        or q in SPECS[t].get("tlabel", "").lower()]

    def pip_install(self, pkg):
        self.root.configure(cursor="watch")
        self.root.update()
        try:
            r = subprocess.run([FROZEN_PYTHON or sys.executable, "-m", "pip", "install", pkg],
                               capture_output=True, text=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as ex:
            return False, str(ex)
        finally:
            self.root.configure(cursor="")
        importlib.invalidate_caches()
        return r.returncode == 0, (r.stdout + r.stderr)[-700:]

    def style_titlebar(self, win):
        """Dark title bar on Windows 10/11 when the dark theme is on (ignored elsewhere)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            value = ctypes.c_int(1 if split_theme(self.theme_name)[1] == "dark" else 0)
            for attr in (20, 19):               # DWMWA_USE_IMMERSIVE_DARK_MODE (new and old Windows 10 id)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), 4) == 0:
                    break
        except Exception:
            pass

    def ask_string(self, title, prompt, initial="", show=None):
        """Small text-entry window that always follows the current theme.
        Returns the text, or None when cancelled (replaces tkinter's fixed-colour simpledialog)."""
        dialog = tk.Toplevel(self.root, bg=self.BG)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        result = {"value": None}
        body = ttk.Frame(dialog, padding=(16, 14, 16, 14))
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=prompt, justify="left", wraplength=460).pack(anchor="w")
        var = tk.StringVar(value=initial)
        entry = ttk.Entry(body, textvariable=var, width=52, show=show or "")
        entry.pack(fill="x", pady=(8, 12))

        def finish(ok):
            result["value"] = var.get() if ok else None
            dialog.destroy()

        row = ttk.Frame(body)
        row.pack(anchor="e")
        ttk.Button(row, text="OK", command=lambda: finish(True)).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Cancel", command=lambda: finish(False)).pack(side="left")
        dialog.bind("<Return>", lambda e: finish(True))
        dialog.bind("<Escape>", lambda e: finish(False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        self.style_titlebar(dialog)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_reqheight()) // 3
        dialog.geometry("+%d+%d" % (max(0, x), max(0, y)))
        entry.focus_set()
        entry.selection_range(0, "end")
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    def try_import(self, name):
        try:
            import_library(name)
            return True
        except ModuleNotFoundError:
            if getattr(sys, "frozen", False) and not FROZEN_PYTHON:
                messagebox.showerror(
                    "Import", "'%s' is not included in this .exe application.\n"
                    "Use scratchpy.py with Python, or rebuild the .exe with "
                    "--hidden-import %s." % (name, name.split(".")[0]))
                return False
            pkg = self.ask_string(
                "Library not found",
                "'%s' is not installed.\nEnter the package name to install with pip "
                "(leave blank to cancel):" % name,
                initial=name.split(".")[0])
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
            name = self.ask_string(
                "Import a library",
                "Python module name (e.g. math, random, string, os.path, turtle, numpy):")
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

    def antialias(self, canvas, polys, cache):
        """Replace the block outlines by smooth pictures (needs Pillow; otherwise keep the vectors)."""
        if not HAVE_PIL or not polys:
            return
        if len(cache) > 1500:
            cache.clear()
        for item, fill, ol, wd in polys:
            try:
                rel, w, h, ox, oy, key = aa_image(canvas.coords(item), fill, ol, wd)
                photo = cache.get(key)
                if photo is None:
                    photo = cache[key] = ImageTk.PhotoImage(aa_render(rel, w, h, fill, ol, wd))
                img = canvas.create_image(ox, oy, image=photo, anchor="nw", tags="shape")
            except Exception:
                return                              # Keep the vector outlines if anything goes wrong.
            canvas.tag_lower(img, item)
            canvas.delete(item)

    def show_palette(self, cat):
        self.cat = cat
        for n, lb in self.cat_labels.items():
            lb.bar.configure(bg="#FFFFFF" if n == cat else lb.dark, height=4)
            lb.configure(font=self.font)
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
        self.antialias(self.pal, r.polys, self.aa_pal)
        bb = self.pal.bbox("shape")
        self.pal.configure(scrollregion=(0, 0, max(320, (bb[2] if bb else 0) + 20), y + 10))
        self.pal.yview_moveto(0)
        self.pal.xview_moveto(0)

    def on_palette_hover(self, event):
        hit = self.palr.find(self.pal.canvasx(event.x), self.pal.canvasy(event.y))
        if not hit or hit[5][0] != "palette":
            self.palette_tip.hide()
            return
        block = hit[4]
        self.palette_tip.move(tr("Add block: %s") % " ".join(v for k, v in block.spec["items"] if k == "t"),
                              event.x_root + 12, event.y_root + 16)

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
            if self._edit_undo_before is None:
                self._edit_undo_before = self.history_snapshot()
            b.fields[idx] = var.get()
            if self._job is None:
                self._job = self.root.after_idle(self.refresh)

    def refresh(self):
        self._job = None
        if self._edit_undo_before is not None:
            before, self._edit_undo_before = self._edit_undo_before, None
            self.commit_undo(before)
        if getattr(self, "find_bar", None) is not None and self.find_bar.winfo_ismapped():
            uids = find_blocks([b for b, ctx, anc in self.iter_blocks()], self.find_var.get())
            self.found = uids                                    # Keep the results up to date while editing.
            if self.found_current not in uids:
                self.found_current = uids[0] if uids else None
            self.update_find_count()
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
        c.create_text(cx, cy - 30, text=tr("Start your program"), fill=self.FG,
                      font=(self.font.actual("family"), 20, "bold"), tags="welcome")
        c.create_text(cx, cy + 12, text=tr("Drag a block from the palette to get started"), fill=self.MUTED,
                      font=(self.font.actual("family"), 13), tags="welcome")
        c.create_text(cx, cy + 40, text=tr("or press Ctrl + O to open a file"),
                  fill=self.MUTED, font=(self.font.actual("family"), 13), tags="welcome")
        c.tag_lower("welcome")

    def render(self, preview=False):
        c, r, z = self.ws, self.wsr, self.zoom
        c.delete("shape")
        r.reset()
        self.used = set()
        r.selected = self.sel
        r.found, r.found_current = set(self.found), self.found_current
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
        self.antialias(c, r.polys, self.aa_ws)
        bb = c.bbox("shape")
        w = max(c.winfo_width(), (bb[2] if bb else 0) + 250)
        h = max(c.winfo_height(), (bb[3] if bb else 0) + 250)
        c.configure(scrollregion=(0, 0, w, h))
        self.draw_welcome()
        self.update_minimap()

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
        if self._code_undo_before is None:
            self._code_undo_before = self.history_snapshot()
            self._code_undo_before["code"] = generate(
                self.scripts, self.libs, self.paths, self.import_lines)
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
        try:                                    # Preserve blocks when only whitespace changed.
            generated_src = generate(self.scripts, self.libs, self.paths, self.import_lines)
            if (ast.dump(tree) == ast.dump(ast.parse(generated_src))      # Same program and same comments:
                    and list(_collect_comments(src).values()) ==         # keep the layout of the blocks.
                    list(_collect_comments(generated_src).values())):
                self._code_undo_before = None
                return
        except Exception:
            pass
        try:
            blocks, imports, paths = python_to_project(src, generated=True)
        except Exception as ex:
            self.set_code_status(ex)
            return
        undo_before, self._code_undo_before = self._code_undo_before, None
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
        self.commit_undo(undo_before)

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
        before = self.history_snapshot() if roots else None
        for b, ctx in roots:
            self.detach(b, ctx)
        self.sel = set()
        self.scripts = [s for s in self.scripts if s.blocks]
        if roots:
            self.refresh()
            self.commit_undo(before)
        return "break"

    def duplicate_selected(self, ev=None):
        groups = self.selection_groups()
        if not groups:
            return "break"
        before = self.history_snapshot()
        new = set()
        for g in groups:
            clones = [from_dict(to_dict(b)) for b in g["blocks"]]
            self.scripts.append(Script(g["x"] + 30, g["y"] + 30, clones))
            new.update(c.uid for c in clones)
        self.sel = new
        self.refresh()
        self.commit_undo(before)
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
        before = self.history_snapshot()
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
        self.commit_undo(before)
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
        before = self.history_snapshot()
        gx, gy = groups[0]["x"], groups[0]["y"]
        for g in groups:
            g["dx"], g["dy"] = g["x"] - gx, g["y"] - gy
        for b, ctx in self.sel_roots():
            self.detach(b, ctx)
        self.scripts = [s for s in self.scripts if s.blocks]
        self.drag = {"blocks": groups[0]["blocks"], "off": (cx - gx, cy - gy),
                 "x": gx, "y": gy, "undo_before": before}
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
        before = self.history_snapshot()
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
        self.drag = {"blocks": blocks, "off": (cx - x, cy - y), "x": x, "y": y,
                 "undo_before": before}
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
            self.commit_undo(d.get("undo_before"))
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
        self.commit_undo(d.get("undo_before"))

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
            before = self.history_snapshot()
            if ctx[0] == "list":
                clones = [from_dict(to_dict(k)) for k in ctx[1][ctx[2]:]]
            else:
                clones = [from_dict(to_dict(b))]
            self.scripts.append(Script(x + 30, y + 30, clones))
            self.refresh()
            self.commit_undo(before)

        def delete():
            before = self.history_snapshot()
            if ctx[0] == "list":
                ctx[1].pop(ctx[2])
            elif ctx[0] == "slot":
                ctx[1].fields[ctx[2]] = ""
            else:
                self.scripts.remove(ctx[1])
            self.scripts = [s for s in self.scripts if s.blocks]
            self.refresh()
            self.commit_undo(before)

        menu.add_command(label="Duplicate", command=dup)
        menu.add_command(label="Delete this block", command=delete)
        menu.tk_popup(e.x_root, e.y_root)
        return "break"

    # ---------- project ----------
    def set_scripts(self, scripts):
        self.stop()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._edit_undo_before = None
        self._code_undo_before = None
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

    def update_autosave_status(self):
        if not hasattr(self, "autosave_status_var"):
            return
        try:
            modified = os.path.getmtime(self.autosave_path)
        except OSError:
            self.autosave_status_var.set("No automatic backup yet")
            return
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified))
        self.autosave_status_var.set("Last backup: %s" % stamp)

    def autosave_is_newer(self):
        if not os.path.isfile(self.autosave_path):
            return False
        try:
            backup_time = os.path.getmtime(self.autosave_path)
            if self.project_path and os.path.isfile(self.project_path):
                return backup_time > os.path.getmtime(self.project_path)
            return True
        except OSError:
            return False

    def project_data(self):
        return {"version": 1, "paths": self.paths, "libs": self.libs,
                "imports": self.import_lines, "scripts": [
            {"x": s.x, "y": s.y, "blocks": [to_dict(b) for b in s.blocks]}
            for s in self.scripts], "code": self.current_code()}

    def history_snapshot(self):
        return json.loads(json.dumps(self.project_data(), ensure_ascii=False))

    def commit_undo(self, before):
        if before is None:
            return
        current = self.history_snapshot()
        if current == before:
            return
        self.undo_stack.append(before)
        del self.undo_stack[:-self.undo_limit]
        self.redo_stack.clear()

    def restore_history_snapshot(self, snapshot):
        if self._code_job:                      # A pending code edit must not overwrite the restored state.
            self.root.after_cancel(self._code_job)
            self._code_job = None
        self._edit_undo_before = None
        self._code_undo_before = None
        self.stop_drag()
        for module in list(self.libs):
            unload_library(module)
        self.libs = []
        self.paths = list(snapshot.get("paths", []))
        for path in self.paths:
            if path not in sys.path:
                sys.path.insert(0, path)
        self.import_lines = list(snapshot.get("imports", []))
        for module in snapshot.get("libs", []):
            try:
                import_library(module)
            except Exception:
                continue
            self.libs.append(module)
        self.scripts = [
            Script(item["x"], item["y"], [from_dict(block) for block in item["blocks"]])
            for item in snapshot.get("scripts", [])
        ]
        self.sel = set()
        code = snapshot.get("code", "")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", code)
        self.code.edit_modified(False)
        self.code_error = None
        self.set_code_status(None)
        self.build_cats()
        self.show_palette(self.cat if self.cat in CATS else "Control")
        self.render()

    def undo(self, ev=None):
        if not self.undo_stack:
            return "break"
        self.redo_stack.append(self.history_snapshot())
        snapshot = self.undo_stack.pop()
        self.restore_history_snapshot(snapshot)
        return "break"

    def redo(self, ev=None):
        if not self.redo_stack:
            return "break"
        self.undo_stack.append(self.history_snapshot())
        snapshot = self.redo_stack.pop()
        self.restore_history_snapshot(snapshot)
        return "break"

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
                data = self.project_data()
                data["_autosave_timestamp"] = time.time()
                json.dump(data, output, ensure_ascii=False, indent=1)
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
        self.update_autosave_status()
        return True

    def autosave_tick(self):
        self.autosave_job = None
        if self.closing:
            return
        self.write_autosave()
        self.autosave_job = self.root.after(self.autosave_interval, self.autosave_tick)

    def restore_autosave(self):
        if not self.autosave_is_newer():
            if os.path.isfile(self.autosave_path):
                try:
                    os.remove(self.autosave_path)
                except OSError:
                    pass
                self.update_autosave_status()
            return
        if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py"):
            return
        if messagebox.askyesno(
                "Restore autosave?", "An automatically saved project was found. Restore it?",
                parent=self.root):
            self.open_file(self.autosave_path)
            self.autosaved_state = self.project_state()
            self.saved_state = None             # Restored work is not saved yet: ask before closing.
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
        self.project_path = None
        self.cfg.pop("project_path", None)
        save_config(self.cfg)
        self.mark_saved()

    def load_example(self, name=None):
        """Replace the workspace with one of the built-in examples (asks before discarding work)."""
        name = name or next(iter(EXAMPLES))
        if self.scripts and self.project_state() != self.saved_state:
            if not messagebox.askyesno("Examples", "Replace the current blocks with the example "
                                       "'%s'?" % name, parent=self.root):
                return
        try:
            blocks, imports, _ = python_to_project(EXAMPLES[name])
        except Exception as ex:                           # Never expected: examples are tested.
            messagebox.showerror("Examples", "Could not load the example:\n%s" % ex)
            return
        self.import_lines = []
        for mod, line in imports:
            if line not in self.import_lines:
                self.import_lines.append(line)
            if mod != "__future__" and self.try_import(mod) and mod not in self.libs:
                self.libs.append(mod)
        self.set_scripts([Script(30, 30, [Block("start")] + blocks)])
        self.project_path = None
        self.cfg.pop("project_path", None)
        save_config(self.cfg)
        self.mark_saved()

    def choose_language(self, ev=None):
        code = next((c for c, n in LANGUAGES if n == self.language_var.get()), "en")
        if code == self.cfg.get("language", "en"):
            return
        self.cfg["language"] = code
        save_config(self.cfg)
        messagebox.showinfo("Language", _LANGUAGE_NOTICE.get(code, _LANGUAGE_NOTICE["en"]), parent=self.root)

    def show_examples_menu(self, anchor):
        menu = tk.Menu(self.root, tearoff=0)
        for name in EXAMPLES:
            menu.add_command(label=name, command=lambda n=name: self.load_example(n))
        menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

    # ---------- recent files ----------
    def add_recent(self, path):
        self.cfg["recent"] = push_recent(self.cfg.get("recent", []), path)
        save_config(self.cfg)

    def show_recent_menu(self, anchor):
        menu = tk.Menu(self.root, tearoff=0)
        items = [p for p in self.cfg.get("recent", []) if isinstance(p, str) and os.path.exists(p)]
        for p in items:
            menu.add_command(label="%s    —    %s" % (os.path.basename(p), os.path.dirname(p)),
                             command=lambda p=p: self.open_file(p))
        if not items:
            menu.add_command(label="(no recent files)", state="disabled")
        else:
            menu.add_separator()
            menu.add_command(label="Clear the list", command=self.clear_recent)
        menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())

    def clear_recent(self):
        self.cfg["recent"] = []
        save_config(self.cfg)

    # ---------- keyboard shortcuts ----------
    def shortcut_map(self):
        custom = self.cfg.get("shortcuts", {})
        return {a: (custom.get(a) if isinstance(custom.get(a), str) else d)
                for a, _, d in SHORTCUT_ACTIONS}

    def shortcut_actions(self):
        return {"run": self.run, "stop": self.stop, "new": self.new, "open": self.open_file,
                "save": self.save_file, "find": self.show_find,
                "find_next": lambda: self.find_step(1), "find_prev": lambda: self.find_step(-1),
                "shortcuts": self.show_shortcuts}

    def bind_shortcuts(self):
        for seq in self.bound_shortcuts:
            try:
                self.root.unbind_all(seq)
            except tk.TclError:
                pass
        self.bound_shortcuts = []
        actions = self.shortcut_actions()
        for action, seq in self.shortcut_map().items():
            variants = {seq}
            tail = seq.strip("<>").split("-")[-1]
            if len(tail) == 1 and tail.isalpha():
                variants.add(seq[:-2] + tail.upper() + ">")
            for v in variants:
                try:
                    self.root.bind_all(v, lambda e, f=actions[action]: (f(), "break")[1])
                    self.bound_shortcuts.append(v)
                except tk.TclError:
                    pass

    def show_shortcuts(self):
        """Help window listing the shortcuts; the customizable ones can be changed."""
        old = getattr(self, "shortcuts_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        dialog = self.shortcuts_win = tk.Toplevel(self.root)
        dialog.title("Keyboard shortcuts")
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Customizable shortcuts", font=self.font).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        buttons = {}

        def refresh_buttons():
            m = self.shortcut_map()
            for a, b in buttons.items():
                b.configure(text=seq_label(m[a]))

        def capture(action):
            b = buttons[action]
            b.configure(text="Press a key…")

            def on_key(ev):
                seq = event_to_seq(ev)
                if seq is None:
                    return "break"
                dialog.unbind("<Key>")
                if ev.keysym == "Escape":
                    refresh_buttons()
                    return "break"
                clash = shortcut_conflicts(self.shortcut_map(), action, seq)
                if clash:
                    names = dict((a, l) for a, l, _ in SHORTCUT_ACTIONS)
                    messagebox.showwarning("Keyboard shortcuts", "%s is already used by “%s”." % (
                        seq_label(seq), names[clash[0]]), parent=dialog)
                else:
                    self.cfg.setdefault("shortcuts", {})[action] = seq
                    save_config(self.cfg)
                    self.bind_shortcuts()
                refresh_buttons()
                return "break"
            dialog.bind("<Key>", on_key)
            dialog.focus_set()

        def reset():
            self.cfg.pop("shortcuts", None)
            save_config(self.cfg)
            self.bind_shortcuts()
            refresh_buttons()

        for i, (action, label, _) in enumerate(SHORTCUT_ACTIONS, start=1):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", padx=(0, 18), pady=2)
            b = ttk.Button(body, width=16, command=lambda a=action: capture(a))
            b.grid(row=i, column=1, sticky="e", pady=2)
            buttons[action] = b
        r = len(SHORTCUT_ACTIONS) + 1
        ttk.Separator(body).grid(row=r, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(body, text="Fixed shortcuts", font=self.font).grid(
            row=r + 1, column=0, columnspan=3, sticky="w", pady=(0, 6))
        for j, (keys, what) in enumerate(FIXED_SHORTCUTS, start=r + 2):
            ttk.Label(body, text=what).grid(row=j, column=0, sticky="w", pady=1)
            ttk.Label(body, text=keys).grid(row=j, column=1, sticky="e", pady=1)
        foot = ttk.Frame(body)
        foot.grid(row=r + 2 + len(FIXED_SHORTCUTS), column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(foot, text="Reset to defaults", command=reset).pack(side="left")
        ttk.Button(foot, text="Close", command=dialog.destroy).pack(side="right")
        refresh_buttons()
        dialog.bind("<Escape>", lambda e: dialog.destroy())
        try:
            self.style_titlebar(dialog)
        except Exception:
            pass

    # ---------- minimap ----------
    MINIMAP_W, MINIMAP_H = 170, 110

    def build_minimap(self, parent):
        self.minimap = tk.Canvas(parent, width=self.MINIMAP_W, height=self.MINIMAP_H,
                                 highlightthickness=1, bd=0, cursor="hand2")
        self.minimap_geo = None
        self.minimap.bind("<Button-1>", self.minimap_click)
        self.minimap.bind("<B1-Motion>", self.minimap_click)
        self.minimap_shown = False

    def set_minimap(self, on):
        self.minimap_on = bool(on)
        self.cfg["minimap"] = self.minimap_on
        save_config(self.cfg)
        self.update_minimap()

    def update_minimap(self):
        """Redraw the overview: block outlines and the visible area."""
        m = getattr(self, "minimap", None)
        if m is None:
            return
        c = self.ws
        bb = c.bbox("shape") if self.scripts else None
        if not self.minimap_on or not bb:
            if self.minimap_shown:
                m.place_forget()
                self.minimap_shown = False
            return
        if not self.minimap_shown:
            m.place(relx=1.0, rely=1.0, x=-22, y=-22, anchor="se")
            self.minimap_shown = True
        m.configure(bg=c.cget("bg"), highlightbackground=self.BORDER)
        try:
            _, _, sw, sh = (float(v) for v in str(c.cget("scrollregion")).split())
        except ValueError:
            return
        W, H = self.MINIMAP_W, self.MINIMAP_H
        sw, sh = max(sw, 1.0), max(sh, 1.0)
        k = min((W - 8) / sw, (H - 8) / sh)
        ox, oy = 4, 4
        self.minimap_geo = (k, ox, oy, sw, sh)
        m.delete("all")
        z = self.zoom
        for h in self.wsr.hits[:600]:
            x0, y0 = h[0] * z * k + ox, h[1] * z * k + oy
            x1, y1 = x0 + max(1.0, h[2] * z * k), y0 + max(1.0, h[3] * z * k)
            m.create_rectangle(x0, y0, x1, y1, outline="", fill=self.MUTED)
        vx0, vy0 = c.canvasx(0), c.canvasy(0)
        vx1, vy1 = vx0 + c.winfo_width(), vy0 + c.winfo_height()
        m.create_rectangle(vx0 * k + ox, vy0 * k + oy, min(vx1, sw) * k + ox, min(vy1, sh) * k + oy,
                           outline=self.ACCENT, width=2)

    def minimap_click(self, ev):
        geo = self.minimap_geo
        if not geo:
            return "break"
        k, ox, oy, sw, sh = geo
        c = self.ws
        x = (ev.x - ox) / k - c.winfo_width() / 2
        y = (ev.y - oy) / k - c.winfo_height() / 2
        c.xview_moveto(max(0.0, min(1.0, x / sw)))
        c.yview_moveto(max(0.0, min(1.0, y / sh)))
        return "break"

    # ---------- drag and drop of files onto the window ----------
    def enable_file_drop(self):
        """Windows only: accept .py / project files dropped on the window (no extra package needed)."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes
            user32, shell32 = ctypes.windll.user32, ctypes.windll.shell32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            WM_DROPFILES, GWL_WNDPROC = 0x0233, -4
            LRESULT = ctypes.c_ssize_t
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            user32.CallWindowProcW.restype = LRESULT
            user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                               wintypes.WPARAM, wintypes.LPARAM]
            shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
            shell32.DragFinish.argtypes = [ctypes.c_void_p]
            old = {}

            def proc(h, msg, wp, lp):
                if msg == WM_DROPFILES:
                    files = []
                    n = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                    for i in range(n):
                        buf = ctypes.create_unicode_buffer(1024)
                        shell32.DragQueryFileW(wp, i, buf, 1024)
                        files.append(buf.value)
                    shell32.DragFinish(wp)
                    self.root.after(10, lambda: self.open_dropped(files))
                    return 0
                return user32.CallWindowProcW(old["p"], h, msg, wp, lp)

            self._drop_proc = WNDPROC(proc)                         # Keep a reference alive.
            old["p"] = user32.SetWindowLongPtrW(hwnd, GWL_WNDPROC,
                                                ctypes.cast(self._drop_proc, ctypes.c_void_p))
            shell32.DragAcceptFiles(hwnd, True)
        except Exception:
            pass

    def open_dropped(self, files):
        for f in files:
            if f.lower().endswith((".py", ".pyw", ".json")):
                self.open_file(f)
                return
        if files:
            messagebox.showinfo("Open", "Drop a Python (.py) file or a ScratchPy project (.json).",
                                parent=self.root)

    def save_as(self):
        return self.save_file(save_as=True)

    def save_file(self, save_as=False):
        path = self.project_path if not save_as else None
        if not path or not os.path.isdir(os.path.dirname(path)):
            path = filedialog.asksaveasfilename(
                defaultextension=".json", initialfile="ScratchPy project.json",
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
        self.project_path = os.path.abspath(path)
        self.cfg["project_path"] = self.project_path
        self.add_recent(self.project_path)
        self.mark_saved()
        self.autosaved_state = self.project_state()
        try:
            os.remove(self.autosave_path)
        except FileNotFoundError:
            pass
        except OSError:
            pass
        self.update_autosave_status()
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
        self.project_path = None
        self.cfg.pop("project_path", None)
        self.add_recent(path)
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
        loaded_path = os.path.abspath(path)
        if os.path.normcase(loaded_path) != os.path.normcase(os.path.abspath(self.autosave_path)):
            self.project_path = loaded_path
            self.cfg["project_path"] = self.project_path
            self.add_recent(loaded_path)
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
        if "console" in self.panel_hidden:          # The output must be visible.
            self.set_panel_visible("console", True)
        self.console_ai_btn.pack_forget()
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
            if end != 0:
                self.console_ai_btn.pack(side="right", padx=6)
            else:
                self.console_ai_btn.pack_forget()
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
        self.ai_write(tr("Hello! I'm ScratchPy's programming assistant (Gemini).\n"
                         "Ask me for a program, an explanation, or help fixing an error. "
                         "I can use your current code and console output. "
                         "Requests are sent to the ScratchPy server."), "info")

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

    def ask_gemini(self, ev=None, prompt=None, display=None):
        from_entry = prompt is None
        prompt = (self.ai_var.get() if from_entry else prompt).strip()
        if not prompt or self.ai_busy:
            return
        if from_entry:
            self.ai_var.set("")
        self.ai_write("You: " + (display or prompt), "user")
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

    def ai_quick(self, kind):
        """Explain / Fix / Optimize: the selected code, or the whole program when nothing is selected."""
        if "assistant" in self.panel_hidden:
            self.set_panel_visible("assistant", True)
        label, text = QUICK_PROMPTS[kind]
        try:
            snippet = self.code.get("sel.first", "sel.last")
        except tk.TclError:
            snippet = ""
        if snippet.strip():
            self.ask_gemini(prompt="%s\n```python\n%s\n```" % (text, snippet.strip("\n")),
                            display="%s (selected code)" % label)
        else:
            self.ask_gemini(prompt=text, display="%s (whole program)" % label)

    def ai_fix_console(self):
        if "assistant" in self.panel_hidden:
            self.set_panel_visible("assistant", True)
        self.ask_gemini(prompt="My program stopped with an error (see the console output). "
                               "Explain what went wrong and give the complete corrected program.",
                        display="Fix the console error")

    def show_diff(self, old, new):
        """Window comparing the current code with the suggestion; returns True to apply it."""
        lines = diff_lines(old, new)
        if not lines:
            messagebox.showinfo("AI assistant", "The suggested code is identical to your code.", parent=self.root)
            return False
        pal = self.theme_colors
        dialog = tk.Toplevel(self.root, bg=pal["BG"])
        dialog.title("Review the suggested changes")
        dialog.transient(self.root)
        dialog.geometry("760x460")
        result = {"ok": False}
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Lines in red will be removed, lines in green will be added.").pack(anchor="w")
        btns = ttk.Frame(body)
        btns.pack(side="bottom", anchor="e", pady=(8, 0))
        box = ttk.Frame(body)
        box.pack(fill="both", expand=True, pady=(6, 0))
        sb = ttk.Scrollbar(box, orient="vertical")
        sb.pack(side="right", fill="y")
        txt = tk.Text(box, bg=pal["EDIT"], fg=pal["FG"], font=tkfont.nametofont("TkFixedFont"), wrap="none",
                      bd=0, padx=8, pady=6, yscrollcommand=sb.set)
        sb.configure(command=txt.yview)
        txt.pack(fill="both", expand=True)
        dark = split_theme(self.theme_name)[1] == "dark"
        txt.tag_configure("add", background="#17422a" if dark else "#d3f5df")
        txt.tag_configure("del", background="#52201f" if dark else "#fcdcda")
        txt.tag_configure("hunk", foreground=pal["ACCENT"])
        for tag, line in lines:
            txt.insert("end", line + "\n", tag)
        txt.configure(state="disabled")

        def finish(ok):
            result["ok"] = ok
            dialog.destroy()

        ttk.Button(btns, text="Apply", command=lambda: finish(True)).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Cancel", command=lambda: finish(False)).pack(side="left")
        dialog.bind("<Escape>", lambda e: finish(False))
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        self.style_titlebar(dialog)
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["ok"]

    def suggest_code_injection(self, new_code):
        if not self.show_diff(self.current_code(), new_code.rstrip("\n") + "\n"):
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
    global FROZEN_PYTHON
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
    FROZEN_PYTHON = setup_frozen_python()
    set_language(load_config().get("language", "en"))
    install_i18n()
    apply_block_language()
    app = App(root)
    root.update_idletasks()
    app.enable_file_drop()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".py"):
        app.open_file(sys.argv[1])
    root.mainloop()


if __name__ == "__main__":
    main()