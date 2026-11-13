#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""极简本地知识库：索引 md/txt -> BM25 检索 -> 可当 MCP server 给 AI 用。

用法:
    python kb.py index  <目录>            # 建索引（默认写 .kb/index.json）
    python kb.py search "<问题>" -k 5     # 命令行检索
    python kb.py mcp                      # 以 MCP server(stdio) 运行
"""
import argparse
import json
import math
import os
import re
import sys
import time

# Windows 控制台默认 GBK，这里统一按 UTF-8 读写，避免中文/符号报错
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:      # noqa: BLE001
        pass

CJK = '\u4e00-\u9fff'
CJK_RUN = re.compile('[' + CJK + ']+')
WORD = re.compile(r'[a-z0-9_]+')
HEAD = re.compile(r'^(#{1,6})\s+(.*)$')
MAX_CHUNK = 900
MIN_CHUNK = 30
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_INDEX = os.path.join(ROOT, '.kb', 'index.json')
SKIP_DIRS = {'.git', '.obsidian', '.kb', 'node_modules', '.trash', '.smart-env', '.venv'}
EXTS = ('.md', '.markdown', '.txt')


def tokenize(text):
    """英文按词，中文按单字 + 相邻二字（bigram），无需分词库。"""
    text = text.lower()
    toks = WORD.findall(text)
    for run in CJK_RUN.findall(text):
        if len(run) == 1:
            toks.append(run)
        else:
            for i in range(len(run) - 1):
                toks.append(run[i:i + 2])
    return toks


def split_sections(lines, start):
    """按 markdown 标题切成 (heading, start_line, end_line)。"""
    out, cur_h, cur_s = [], '', start
    for i in range(start, len(lines)):
        m = HEAD.match(lines[i])
        if m:
            out.append((cur_h, cur_s, i))
            cur_h, cur_s = m.group(2).strip(), i
    out.append((cur_h, cur_s, len(lines)))
    return out


def split_section(lines, s, e, heading):
    """一段太长就按行数/字数再切，保留精确行号。"""
    chunks, buf, buf_start = [], [], None

    def flush(end):
        nonlocal buf, buf_start
        text = '\n'.join(buf).strip()
        if text:
            chunks.append({'heading': heading, 'start': buf_start, 'end': end, 'text': text})
        buf, buf_start = [], None

    for i in range(s, e):
        if buf_start is None:
            buf_start = i + 1
        buf.append(lines[i])
        if len('\n'.join(buf)) >= MAX_CHUNK:
            flush(i + 1)
    flush(e)
    return chunks


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.lower().endswith(EXTS):
                yield os.path.join(dirpath, fn)


def build_index(root):
    chunks = []
    for path in iter_files(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        start = 0
        if lines and lines[0].strip() == '---':          # 跳过 YAML frontmatter
            for i in range(1, min(len(lines), 80)):
                if lines[i].strip() == '---':
                    start = i + 1
                    break
        for heading, s, e in split_sections(lines, start):
            for ch in split_section(lines, s, e, heading):
                toks = tokenize(ch['text'])
                if len(ch['text']) < MIN_CHUNK and not heading:
                    continue
                ch['path'] = rel
                ch['len'] = len(toks)
                tf = {}
                for t in toks:
                    tf[t] = tf.get(t, 0) + 1
                ch['tf'] = tf
                chunks.append(ch)

    df = {}
    for ch in chunks:
        for t in ch['tf']:
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    avgdl = (sum(c['len'] for c in chunks) / n) if n else 0.0
    return {
        'version': 1,
        'root': os.path.abspath(root),
        'built_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'n': n,
        'avgdl': avgdl,
        'df': df,
        'chunks': [{'path': c['path'], 'heading': c['heading'], 'start': c['start'],
                    'end': c['end'], 'text': c['text'], 'len': c['len'], 'tf': c['tf']}
                   for c in chunks],
    }


def load_index(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def search(idx, query, k=5):
    toks = tokenize(query)
    if not toks or not idx['chunks']:
        return []
    N, avgdl, df = idx['n'], idx['avgdl'] or 1.0, idx['df']
    k1, b = 1.2, 0.75
    idf = {}
    for t in set(toks):
        d = df.get(t, 0)
        idf[t] = math.log(1 + (N - d + 0.5) / (d + 0.5))
    scored = []
    for ci, ch in enumerate(idx['chunks']):
        dl, tf = ch['len'], ch['tf']
        s = 0.0
        for t in set(toks):
            f = tf.get(t, 0)
            if f:
                s += idf[t] * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scored.append((s, ci))
    scored.sort(reverse=True)
    return [(sc, idx['chunks'][ci]) for sc, ci in scored[:k]]


def snippet(text, query, width=160):
    low = text.lower()
    pos = -1
    for t in sorted(set(tokenize(query)), key=len, reverse=True):
        p = low.find(t)
        if p >= 0:
            pos = p
            break
    if pos < 0:
        pos = 0
    a = max(0, pos - width // 3)
    frag = ' '.join(text[a:a + width].split())
    return ('…' if a > 0 else '') + frag + '…'


def cmd_search(idx_path, query, k):
    idx = load_index(idx_path)
    hits = search(idx, query, k)
    if not hits:
        print('（没有命中，试试换个说法）')
        return
    for rank, (score, ch) in enumerate(hits, 1):
        head = f"{ch['path']}" + (f" > {ch['heading']}" if ch['heading'] else '')
        print(f'[{rank}] {head}  (L{ch["start"]}-{ch["end"]}, score={score:.2f})')
        print('    ' + snippet(ch['text'], query))
    print(f'\n共 {len(idx["chunks"])} 个知识块，来自 {len(set(c["path"] for c in idx["chunks"]))} 个文件')


TOOLS = [
    {
        'name': 'search_notes',
        'description': '在本地笔记/知识库中检索，返回最相关的片段（含文件路径与行号）。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': '自然语言问题或关键词'},
                'k': {'type': 'integer', 'description': '返回条数，默认 5'},
            },
            'required': ['query'],
        },
    },
    {
        'name': 'read_note',
        'description': '按路径读取笔记内容，可指定行范围。',
        'inputSchema': {
            'type': 'object',
            'properties': {
                'path': {'type': 'string'},
                'start': {'type': 'integer'},
                'end': {'type': 'integer'},
            },
            'required': ['path'],
        },
    },
    {
        'name': 'list_notes',
        'description': '列出知识库里的所有笔记文件。',
        'inputSchema': {'type': 'object', 'properties': {}},
    },
]


def call_tool(idx, name, args):
    if name == 'search_notes':
        q = args.get('query', '')
        k = int(args.get('k') or 5)
        hits = search(idx, q, k)
        if not hits:
            return '没有找到相关内容。'
        out = []
        for sc, ch in hits:
            head = ch['path'] + (f" > {ch['heading']}" if ch['heading'] else '')
            out.append(f"### {head} (L{ch['start']}-{ch['end']})\n{ch['text'][:1200]}")
        return '\n\n'.join(out)
    if name == 'read_note':
        path = args.get('path', '')
        root = idx['root']
        full = os.path.abspath(os.path.join(root, path))
        if not full.startswith(os.path.abspath(root)):
            return '拒绝：路径越界'
        with open(full, encoding='utf-8', errors='replace') as f:
            lines = f.read().splitlines()
        s = int(args.get('start') or 1)
        e = int(args.get('end') or len(lines))
        return '\n'.join(f'{i + 1}: {lines[i]}' for i in range(max(0, s - 1), min(len(lines), e)))
    if name == 'list_notes':
        return '\n'.join(sorted(set(c['path'] for c in idx['chunks'])))
    raise ValueError(f'unknown tool: {name}')


def mcp_main(idx_path):
    idx = load_index(idx_path)

    def send(obj):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
        sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid = msg.get('id')
        method = msg.get('method', '')
        if method == 'initialize':
            send({'jsonrpc': '2.0', 'id': mid, 'result': {
                'protocolVersion': '2024-11-05',
                'capabilities': {'tools': {}},
                'serverInfo': {'name': 'local-kb', 'version': '0.1.0'},
            }})
        elif method == 'notifications/initialized' or mid is None:
            continue
        elif method == 'tools/list':
            send({'jsonrpc': '2.0', 'id': mid, 'result': {'tools': TOOLS}})
        elif method == 'tools/call':
            name = msg['params'].get('name')
            args = msg['params'].get('arguments') or {}
            try:
                text = call_tool(idx, name, args)
                send({'jsonrpc': '2.0', 'id': mid, 'result': {
                    'content': [{'type': 'text', 'text': text}], 'isError': False}})
            except Exception as exc:                     # noqa: BLE001
                send({'jsonrpc': '2.0', 'id': mid, 'result': {
                    'content': [{'type': 'text', 'text': f'错误: {exc}'}], 'isError': True}})
        elif method == 'ping':
            send({'jsonrpc': '2.0', 'id': mid, 'result': {}})
        else:
            send({'jsonrpc': '2.0', 'id': mid,
                  'error': {'code': -32601, 'message': f'method not found: {method}'}})


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p1 = sub.add_parser('index')
    p1.add_argument('root')
    p1.add_argument('--out', default=DEFAULT_INDEX)
    p2 = sub.add_parser('search')
    p2.add_argument('query')
    p2.add_argument('-k', type=int, default=5)
    p2.add_argument('--index', default=DEFAULT_INDEX)
    p3 = sub.add_parser('mcp')
    p3.add_argument('--index', default=DEFAULT_INDEX)
    a = ap.parse_args()

    if a.cmd == 'index':
        idx = build_index(a.root)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, 'w', encoding='utf-8') as f:
            json.dump(idx, f, ensure_ascii=False)
        print(f"索引完成: {idx['n']} 块 / {len(set(c['path'] for c in idx['chunks']))} 文件 -> {a.out}")
    elif a.cmd == 'search':
        cmd_search(a.index, a.query, a.k)
    elif a.cmd == 'mcp':
        mcp_main(a.index)


if __name__ == '__main__':
    main()
