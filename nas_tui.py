#!/usr/bin/env python3
"""physis-nas TUI: scan (algo/semantic), browse/zoom, agentic Q/A, evidence, correction.

A selector-driven console over one physis world model:

- SCAN   — algo mode runs structural query + BM25 body search; semantic mode
           runs `physis explore` (bounded retrieval packet with receipts and
           freshness). Both are labeled with what they actually are.
- BROWSE — walk the world's tree, zoom into one object's bounded context packet.
- Q/A    — agentic question loop: model-free `chat` first (every answer carries
           its evidence), falling back to `ask` (primitive-compiled, confidence
           gated). UNKNOWN is shown as UNKNOWN, never dressed up.
- EVIDENCE — for the selected object: why it exists, its provenance chain, its
           bounded context. Reality is tracked, not asserted.
- CORRECT — append-only reality correction: `remember` writes a correction note
           as a new observation; `values` shows effective fields with typed
           corrections applied. Nothing is ever rewritten.

Everything is read-only on the scanned tree. The store is whatever
PHYSIS_STORE_DIR points at; this tool never writes inside the observed root.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

DEFAULT_PHYSIS = '/home/gio/dev/physis-next/target/debug/physis'
DEFAULT_STORE = '/home/gio/.physis-nas-world'


def build_env(store):
    env = os.environ.copy()
    env['PHYSIS_STORE_DIR'] = str(store)
    return env


def run_physis(physis, env, args, timeout=60):
    """Run one physis command; return (ok, text). Never raises on nonzero exit."""
    try:
        r = subprocess.run([physis, *args], env=env, capture_output=True,
                           text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f'physis-nas-tui: {exc}'
    if r.returncode:
        return False, (r.stderr or r.stdout).strip() or f'physis exited {r.returncode}'
    return True, r.stdout


def run_json(physis, env, args, timeout=60):
    ok, text = run_physis(physis, env, args, timeout)
    if not ok:
        return False, {'error': text}
    try:
        return True, json.loads(text)
    except json.JSONDecodeError:
        return False, {'error': 'physis did not emit JSON', 'raw': text[:400]}


# ---------- scan modes ----------

SCAN_MODES = {
    'algo': {
        'label': 'ALGO — structural query + BM25 body search',
        'commands': lambda q: [
            ['query', q, '--json'],
            ['search', q, '--limit', '10'],
        ],
    },
    'semantic': {
        'label': 'SEMANTIC — explore packet (retrieval + receipts + freshness)',
        'commands': lambda q: [
            ['explore', q, '--json'],
        ],
    },
}


def render_scan(mode, query, data_by_cmd):
    """Turn raw command outputs into display lines, labeled honestly."""
    lines = [f'[b]{SCAN_MODES[mode]["label"]}[/b]', f'query: {query}', '']
    for args, data in data_by_cmd:
        cmd = args[0]
        if cmd == 'query':
            results = data.get('results', []) if isinstance(data, dict) else []
            lines.append(f'[b]structural query[/b] — {len(results)} results')
            lines += [f'  {r}' for r in results[:15]]
            if not results:
                lines.append('  (no results — an empty result is a finding, not a failure)')
        elif cmd == 'search':
            if isinstance(data, dict):
                hits = data.get('results', data.get('hits', []))
            else:
                hits = [ln for ln in data.splitlines() if ln.strip()][:10]
            lines.append(f'[b]BM25 body search[/b] — {len(hits)} hits')
            lines += [f'  {h}' for h in hits[:10]]
            if not hits:
                lines.append('  (no hits)')
        elif cmd == 'explore':
            lines.append('[b]explore packet[/b]')
            lines.append(f"  world_revision: {data.get('world_revision')}")
            lines.append(f"  fresh: {data.get('fresh')}  stale: {data.get('stale')}  truncated: {data.get('truncated')}")
            orient = data.get('orientation') or []
            lines.append(f'  orientation ({len(orient)}):')
            lines += [f'    {o}' for o in orient[:8]]
            sources = data.get('sources') or []
            lines.append(f'  sources ({len(sources)}):')
            lines += [f'    {s}' for s in sources[:8]]
            receipts = data.get('receipts') or []
            lines.append(f'  receipts ({data.get("receipts_total", len(receipts))}):')
            lines += [f'    {r}' for r in receipts[:6]]
            if not sources and not orient:
                lines.append('  (empty packet — nothing retrieved for this query)')
        lines.append('')
    return lines


# ---------- Q/A ----------

def ask_world(physis, env, question):
    """chat first (model-free, evidence-carrying); fall back to ask.

    Returns (engine, dict). Refusal/UNKNOWN are preserved as-is.
    """
    ok, chat = run_json(physis, env, ['chat', '--once', question, '--json'])
    if ok and isinstance(chat, dict) and chat.get('kind') != 'refusal':
        return 'chat', chat
    ok, ask = run_json(physis, env, ['ask', question, '--json'], timeout=120)
    if ok and isinstance(ask, dict):
        return 'ask', ask
    return 'error', (ask if isinstance(ask, dict) else {'error': 'both engines failed'})


def render_answer(engine, data):
    lines = []
    if engine == 'chat':
        lines.append('[b]engine: chat[/b] (model-free; every claim carries evidence)')
        lines.append(data.get('text', ''))
        ev = data.get('evidence') or data.get('edges') or []
        if ev:
            lines.append(f'[b]evidence ({len(ev)}):[/b]')
            lines += [f'  {e}' for e in ev[:10]]
    elif engine == 'ask':
        card = data.get('card') or {}
        lines.append('[b]engine: ask[/b] (primitive-compiled, confidence-gated)')
        lines.append(f"answer: {data.get('answer')}")
        lines.append(f"confidence: {data.get('confidence')} ({data.get('confidence_source')})")
        if data.get('escalation'):
            lines.append(f"escalation: {data.get('escalation')}")
        steps = (card.get('program') or {}).get('steps') or []
        if steps:
            lines.append('program steps: ' + ', '.join(s.get('primitive_id', '?') for s in steps))
        ev = data.get('evidence') or []
        if ev:
            lines.append(f'[b]evidence ({len(ev)}):[/b]')
            lines += [f'  {e}' for e in ev[:10]]
    else:
        lines.append('[b]engine error[/b]')
        lines.append(str(data.get('error', data)))
    if data.get('answer') == 'UNKNOWN' or data.get('kind') == 'refusal':
        lines.append('[i]UNKNOWN/refusal preserved — the world does not support this question shape; nothing was invented.[/i]')
    return lines


# ---------- world stats ----------

def world_stats(physis, env):
    ok, data = run_json(physis, env, ['explore', 'world', '--json'])
    rev = data.get('world_revision', '?') if ok else '?'
    ok2, hist = run_json(physis, env, ['history', '--limit', '1', '--json'])
    seq = '?'
    if ok2:
        rows = hist.get('rows') or hist.get('observations') or []
        seq = max((int(r['seq']) for r in rows if 'seq' in r), default='?')
    return f'world {rev} · seq {seq}'


# ---------- TUI ----------

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, Static, RichLog, Tabs
from textual.containers import Horizontal, Vertical


class NasTui(App):
    CSS = """
    #body { height: 1fr; }
    #side { width: 34; border-right: solid $accent; padding: 0 1; }
    #main { width: 1fr; }
    Input { dock: bottom; }
    #mode-line { color: $accent; }
    """
    BINDINGS = [
        ('q', 'quit', 'quit'),
        ('1', 'tab("search")', 'search'),
        ('2', 'tab("qa")', 'q/a'),
        ('3', 'tab("evidence")', 'evidence'),
        ('4', 'tab("correct")', 'correct'),
        ('a', 'toggle_mode', 'algo/semantic'),
        ('r', 'refresh_tree', 're-scan tree'),
    ]
    TABS = ['search', 'qa', 'evidence', 'correct']

    def __init__(self, physis, store):
        super().__init__()
        self.physis = physis
        self.env = build_env(store)
        self.mode = 'algo'
        self.selected = None
        self.cwd = ''  # relative path in the world

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id='body'):
            with Vertical(id='side'):
                yield Static(f'MODE: {self.mode}', id='mode-line')
                yield Static('tree (r to refresh)', id='tree-label')
                yield RichLog(id='tree-log', markup=True, wrap=True)
            with Vertical(id='main'):
                yield Tabs(*self.TABS, id='tabs')
                yield RichLog(id='out', markup=True, wrap=True)
        yield Input(placeholder='type a query / question / correction — Enter to run')
        yield Footer()

    def on_mount(self):
        self.query_one('#mode-line', Static).update(f'MODE: {self.mode}  (a to toggle)')
        self.action_refresh_tree()
        self.query_one('#out', RichLog).write('[i]algo/semantic scan, browse/zoom, agentic Q/A over the world model. q quits.[/i]')

    def run_bg(self, fn, tab='out'):
        self.run_worker(fn, thread=True, exclusive=False, group=tab)

    def write_out(self, lines, tab='#out'):
        log = self.query_one(tab, RichLog)
        for ln in lines:
            log.write(ln)

    def _safe(self, fn, *args):
        """Run an UI update from any thread (worker or app thread)."""
        try:
            self.call_from_thread(fn, *args)
        except RuntimeError:
            fn(*args)

    # ----- tree browsing -----
    def action_refresh_tree(self):
        self.run_bg(self._load_tree, tab='tree')

    def _load_tree(self):
        ok, text = run_physis(self.physis, self.env, ['tree', self.cwd or '.'], timeout=30)
        lines = text.splitlines()[:200] if ok else [f'[red]{text}[/red]']
        stats = world_stats(self.physis, self.env)
        self._safe(self._show_tree, lines, stats)

    def _show_tree(self, lines, stats):
        self.title = f'physis-nas — {stats}'
        log = self.query_one('#tree-log', RichLog)
        log.clear()
        for ln in lines:
            log.write(ln)

    # ----- scan -----
    def _do_scan(self, q):
        mode = self.mode
        data_by_cmd = []
        for args in SCAN_MODES[mode]['commands'](q):
            ok, data = run_json(self.physis, self.env, args, timeout=90)
            data_by_cmd.append((args, data if ok else {'error': data}))
        self._safe(self.write_out, render_scan(mode, q, data_by_cmd))

    # ----- Q/A -----
    def _do_ask(self, q):
        engine, data = ask_world(self.physis, self.env, q)
        self._safe(self.write_out, [f'[b]Q:[/b] {q}'] + render_answer(engine, data) + [''])

    # ----- evidence -----
    def _do_evidence(self, obj):
        lines = [f'[b]evidence for[/b] {obj}']
        for label, args in (
            ('why (recorded events; oldest gap shown as UNKNOWN)', ['why', obj]),
            ('subject (provenance chain)', ['subject', obj]),
            ('context (bounded packet)', ['context', obj, '--json']),
        ):
            ok, text = run_physis(self.physis, self.env, args, timeout=60)
            lines.append(f'[b]{label}[/b]')
            lines += [f'  {ln}' for ln in text.splitlines()[:18]] if ok else [f'  [red]{text}[/red]']
            lines.append('')
        self._safe(self.write_out, lines)

    # ----- correction -----
    def _do_correct(self, note):
        ok, text = run_physis(self.physis, self.env, ['remember', note], timeout=30)
        out = [f'[b]correction recorded (append-only):[/b] {note}', text.strip() or ('ok' if ok else f'[red]{text}[/red]'), '']
        self._safe(self.write_out, out if ok else [f'[red]{text}[/red]'])

    # ----- input dispatch -----
    def on_input_submitted(self, event):
        q = event.value.strip()
        if not q:
            return
        event.input.value = ''
        tab = self.query_one('#tabs', Tabs).active
        if tab == 'search':
            self.write_out([f'[b]scan ({self.mode}):[/b] {q}', ''])
            self.run_bg(lambda: self._do_scan(q), tab='out')
        elif tab == 'qa':
            self.run_bg(lambda: self._do_ask(q), tab='out')
        elif tab == 'evidence':
            self.selected = q
            self.run_bg(lambda: self._do_evidence(q), tab='out')
        elif tab == 'correct':
            self.run_bg(lambda: self._do_correct(q), tab='out')

    def on_tabs_activated(self, event):
        pass

    def action_tab(self, name):
        self.query_one('#tabs', Tabs).active = name

    def action_toggle_mode(self):
        self.mode = 'semantic' if self.mode == 'algo' else 'algo'
        self.query_one('#mode-line', Static).update(f'MODE: {self.mode}  (a to toggle)')
        self.write_out([f'[i]scan mode -> {self.mode}[/i]'])


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--physis', default=DEFAULT_PHYSIS)
    p.add_argument('--store', default=DEFAULT_STORE)
    a = p.parse_args()
    if not Path(a.physis).is_file():
        print(f'physis-nas-tui: physis binary not found at {a.physis}', file=sys.stderr)
        return 1
    NasTui(a.physis, a.store).run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
