"""
Math Compiler Backend
Flask REST API + SQLite storage

Endpoints:
  POST /api/calculate       { "expression": "3 + 4 * 2" }  -> { result, tokens, ast }
  GET  /api/history         -> [ { id, expression, result, created_at } ]
  DELETE /api/history/<id>  -> { ok }
  DELETE /api/history       -> { ok }  (clear all)
  GET  /api/stats           -> { total, avg_result, most_used_op }
"""

import re
import math
import json
import sqlite3
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

DB_PATH = os.path.join(os.path.dirname(__file__), "history.db")

# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS calculations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                expression  TEXT    NOT NULL,
                result      REAL    NOT NULL,
                tokens      TEXT    NOT NULL,
                ast_json    TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            )
        """)
        db.commit()

# ─────────────────────────────────────────────
# LEXER
# ─────────────────────────────────────────────

TOKEN_RE = re.compile(
    r'\s*(?:'
    r'(?P<NUM>[0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)'
    r'|(?P<OP>[+\-*/%^])'
    r'|(?P<LP>\()'
    r'|(?P<RP>\))'
    r'|(?P<ERR>.)'
    r')\s*'
)

def tokenize(expr):
    tokens = []
    for m in TOKEN_RE.finditer(expr):
        if m.group('NUM'):
            tokens.append({'type': 'NUM',   'value': m.group('NUM')})
        elif m.group('OP'):
            tokens.append({'type': 'OP',    'value': m.group('OP')})
        elif m.group('LP'):
            tokens.append({'type': 'LPAREN','value': '('})
        elif m.group('RP'):
            tokens.append({'type': 'RPAREN','value': ')'})
        elif m.group('ERR'):
            raise ValueError(f"Unexpected character: '{m.group('ERR')}'")
    tokens.append({'type': 'EOF', 'value': ''})
    return tokens

# ─────────────────────────────────────────────
# PARSER  (recursive descent -> dict AST)
# ─────────────────────────────────────────────

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos]

    def eat(self):
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def parse(self):
        node = self.expr()
        if self.peek()['type'] != 'EOF':
            raise ValueError("Unexpected tokens after expression")
        return node

    def expr(self):
        left = self.term()
        while self.peek()['type'] == 'OP' and self.peek()['value'] in ('+', '-'):
            op = self.eat()['value']
            left = {'type': 'BinOp', 'op': op, 'left': left, 'right': self.term()}
        return left

    def term(self):
        left = self.power()
        while self.peek()['type'] == 'OP' and self.peek()['value'] in ('*', '/', '%'):
            op = self.eat()['value']
            left = {'type': 'BinOp', 'op': op, 'left': left, 'right': self.power()}
        return left

    def power(self):
        base = self.unary()
        if self.peek()['type'] == 'OP' and self.peek()['value'] == '^':
            self.eat()
            return {'type': 'BinOp', 'op': '^', 'left': base, 'right': self.power()}
        return base

    def unary(self):
        if self.peek()['type'] == 'OP' and self.peek()['value'] == '-':
            self.eat()
            return {'type': 'Unary', 'op': '-', 'operand': self.unary()}
        return self.primary()

    def primary(self):
        t = self.peek()
        if t['type'] == 'NUM':
            self.eat()
            return {'type': 'Num', 'value': float(t['value'])}
        if t['type'] == 'LPAREN':
            self.eat()
            inner = self.expr()
            if self.peek()['type'] != 'RPAREN':
                raise ValueError("Expected ')'")
            self.eat()
            return inner
        raise ValueError(f"Unexpected token: '{t['value']}'")

# ─────────────────────────────────────────────
# EVALUATOR
# ─────────────────────────────────────────────

def evaluate(node):
    t = node['type']
    if t == 'Num':
        return node['value']
    if t == 'Unary':
        return -evaluate(node['operand'])
    if t == 'BinOp':
        l, r = evaluate(node['left']), evaluate(node['right'])
        op = node['op']
        if op == '+': return l + r
        if op == '-': return l - r
        if op == '*': return l * r
        if op == '/':
            if r == 0: raise ZeroDivisionError("Division by zero")
            return l / r
        if op == '%':
            if r == 0: raise ZeroDivisionError("Modulo by zero")
            return math.fmod(l, r)
        if op == '^': return math.pow(l, r)
    raise ValueError(f"Unknown node type: {t}")

# ─────────────────────────────────────────────
# COMPILE (all stages)
# ─────────────────────────────────────────────

def compile_and_eval(expression):
    tokens = tokenize(expression.strip())
    ast    = Parser(tokens[:-1] + [tokens[-1]]).parse()  # include EOF
    result = evaluate(ast)
    if math.isnan(result) or math.isinf(result):
        raise ValueError("Result is not a finite number")
    return tokens, ast, result

# ─────────────────────────────────────────────
# HTTP SERVER  (no framework dependency)
# ─────────────────────────────────────────────

def json_response(handler, code, data):
    body = json.dumps(data, default=str).encode()
    handler.send_response(code)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Content-Length', len(body))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    handler.send_header('Access-Control-Allow-Headers', 'Content-Type')
    handler.end_headers()
    handler.wfile.write(body)

def read_json_body(handler):
    length = int(handler.headers.get('Content-Length', 0))
    return json.loads(handler.rfile.read(length)) if length else {}


class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"  {self.command} {self.path} -> {args[1] if len(args)>1 else ''}")

    def do_OPTIONS(self):
        json_response(self, 204, {})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/calculate':
            body = read_json_body(self)
            expr = body.get('expression', '').strip()
            if not expr:
                return json_response(self, 400, {'error': 'Empty expression'})
            try:
                tokens, ast, result = compile_and_eval(expr)
                # Format result
                display = int(result) if result == int(result) and abs(result) < 1e15 else result
                # Save to DB
                with get_db() as db:
                    db.execute(
                        "INSERT INTO calculations (expression, result, tokens, ast_json, created_at) VALUES (?,?,?,?,?)",
                        (expr, result, json.dumps(tokens), json.dumps(ast),
                         datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    )
                    db.commit()
                    row = db.execute("SELECT last_insert_rowid() as id").fetchone()
                    calc_id = row['id']
                return json_response(self, 200, {
                    'id': calc_id,
                    'expression': expr,
                    'result': display,
                    'tokens': tokens,
                    'ast': ast
                })
            except Exception as e:
                return json_response(self, 422, {'error': str(e)})
        json_response(self, 404, {'error': 'Not found'})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == '/api/history':
            with get_db() as db:
                rows = db.execute(
                    "SELECT id, expression, result, created_at FROM calculations ORDER BY id DESC LIMIT 100"
                ).fetchall()
            return json_response(self, 200, [dict(r) for r in rows])

        if path == '/api/stats':
            with get_db() as db:
                total = db.execute("SELECT COUNT(*) as c FROM calculations").fetchone()['c']
                avg   = db.execute("SELECT AVG(result) as a FROM calculations").fetchone()['a']
                # count operators
                ops = {'+':0, '-':0, '*':0, '/':0, '^':0, '%':0}
                rows = db.execute("SELECT expression FROM calculations").fetchall()
                for r in rows:
                    for ch in r['expression']:
                        if ch in ops: ops[ch] += 1
                most = max(ops, key=ops.get) if any(ops.values()) else '-'
            return json_response(self, 200, {
                'total': total,
                'avg_result': round(avg, 4) if avg is not None else 0,
                'most_used_op': most,
                'op_counts': ops
            })

        # Serve frontend
        if path in ('/', ''):
            path = '/index.html'
        file_path = os.path.join(os.path.dirname(__file__), '..', 'frontend', path.lstrip('/'))
        if os.path.isfile(file_path):
            ext = os.path.splitext(file_path)[1]
            ctype = {'html':'text/html','js':'application/javascript','css':'text/css'}.get(ext[1:],'text/plain')
            with open(file_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', len(data))
            self.end_headers()
            self.wfile.write(data)
            return

        json_response(self, 404, {'error': 'Not found'})

    def do_DELETE(self):
        path = urlparse(self.path).path

        if path == '/api/history':
            with get_db() as db:
                db.execute("DELETE FROM calculations")
                db.commit()
            return json_response(self, 200, {'ok': True, 'deleted': 'all'})

        m = re.match(r'^/api/history/(\d+)$', path)
        if m:
            rid = int(m.group(1))
            with get_db() as db:
                db.execute("DELETE FROM calculations WHERE id=?", (rid,))
                db.commit()
            return json_response(self, 200, {'ok': True, 'deleted': rid})

        json_response(self, 404, {'error': 'Not found'})


if __name__ == '__main__':
    init_db()
    PORT = 8000
    server = HTTPServer(('0.0.0.0', PORT), Handler)
    print(f"\n  Math Compiler API running at http://localhost:{PORT}")
    print(f"  Open http://localhost:{PORT} in your browser\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
