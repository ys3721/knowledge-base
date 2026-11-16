#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日待办与总结：创建 / 查看 / 追加 / 勾选 当天的 journal 笔记。

用法:
    python daily.py new             # 创建今天的笔记（已存在则不动）
    python daily.py show            # 查看今天（含完成度）
    python daily.py add "写周报"     # 往「待办」追加一条
    python daily.py done 3          # 勾选/取消第 3 个复选框
    python daily.py close           # 标记今天「已总结」
    python daily.py html            # 生成仪表盘并在浏览器打开（--no-open 只生成）
    python daily.py open            # 用默认程序打开今天的笔记
"""
import argparse
import datetime
import html as html_mod
import os
import re
import sys

for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:      # noqa: BLE001
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JPATH = os.path.join(ROOT, 'journal')
TPATH = os.path.join(ROOT, 'templates', 'daily.md')
WEEK = '一二三四五六日'
CHECK = re.compile(r'^(\s*)- \[( |x|X)\]\s*(.*)$')
HEADING = re.compile(r'^(#{1,6})\s+(.*)$')


def today():
    return datetime.date.today().isoformat()


def day_path(date):
    return os.path.join(JPATH, date + '.md')


def weekday(date):
    return '周' + WEEK[datetime.date.fromisoformat(date).weekday()]


def ensure(date):
    p = day_path(date)
    if os.path.exists(p):
        return p
    os.makedirs(JPATH, exist_ok=True)
    with open(TPATH, encoding='utf-8') as f:
        tpl = f.read()
    text = tpl.replace('{{date}}', date).replace('{{weekday}}', weekday(date))
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    return p


def read_lines(p):
    with open(p, encoding='utf-8') as f:
        return f.read().splitlines()


def write_lines(p, lines):
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def scan(lines):
    """返回 [(行号, 是否勾选, 文本)]，只统计有文字的复选框。"""
    items = []
    for i, ln in enumerate(lines):
        m = CHECK.match(ln)
        if m and m.group(3).strip():
            items.append((i, m.group(2).lower() == 'x', m.group(3).strip()))
    return items


def cmd_new(date):
    p = ensure(date)
    print(p)


def cmd_show(date):
    p = ensure(date)
    lines = read_lines(p)
    items = scan(lines)
    done = sum(1 for _, ok, _ in items if ok)
    print(f'{date} {weekday(date)}    完成 {done}/{len(items)}')
    print('-' * 46)
    sections, cur = [], None
    for ln in lines:
        h = HEADING.match(ln)
        if h:
            cur = {'title': h.group(2).strip() if len(h.group(1)) > 1 else None, 'items': []}
            sections.append(cur)
            continue
        m = CHECK.match(ln)
        if m and m.group(3).strip():
            if cur is None:
                cur = {'title': None, 'items': []}
                sections.append(cur)
            cur['items'].append((m.group(2).lower() == 'x', m.group(3).strip()))
    for s in sections:
        if not s['title'] or not s['items']:
            continue
        print(f"\n [{s['title']}]")
        for ok, text in s['items']:
            print(f'   {"[x]" if ok else "[ ]"} {text}')
    print('\n 提示: add "..." 追加 / done N 勾选 / html 生成仪表盘')


def cmd_add(date, item):
    p = ensure(date)
    lines = read_lines(p)
    start = None
    for i, ln in enumerate(lines):
        if re.match(r'^##\s*待办', ln.strip()):
            start = i
            break
    if start is None:
        raise SystemExit('模板里找不到「## 待办」小节')
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith('##'):
            end = j
            break
    for i in range(start, end):
        m = CHECK.match(lines[i])
        if m and m.group(3).strip() == item:
            print('已存在，跳过')
            return
    pos = None
    for j in range(end - 1, start, -1):
        if CHECK.match(lines[j]) and CHECK.match(lines[j]).group(3).strip():
            pos = j + 1
            break
    if pos is None:
        pos = start + 1
        while pos < end and not lines[pos].strip():
            pos += 1
    lines.insert(pos, f'- [ ] {item}')
    write_lines(p, lines)
    print(f'已加入待办: {item}')


def cmd_done(date, n):
    p = ensure(date)
    lines = read_lines(p)
    items = scan(lines)
    if n < 1 or n > len(items):
        raise SystemExit(f'没有第 {n} 条（今天共 {len(items)} 条）')
    i, checked, text = items[n - 1]
    m = CHECK.match(lines[i])
    box = ' ' if checked else 'x'
    lines[i] = f'{m.group(1)}- [{box}] {m.group(3)}'
    write_lines(p, lines)
    print(('已取消: ' if checked else '已完成: ') + text)


def cmd_close(date):
    p = ensure(date)
    with open(p, encoding='utf-8') as f:
        text = f.read()
    if re.search(r'(?m)^status:', text):
        text = re.sub(r'(?m)^status:.*$', 'status: closed', text, count=1)
    else:
        text = text.replace('---\n', '---\nstatus: closed\n', 1)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print(f'{date} 已标记为已总结')


def cmd_html(date, open_browser):
    p = ensure(date)
    lines = read_lines(p)
    items = scan(lines)
    done = sum(1 for _, ok, _ in items if ok)
    body = []
    for ln in lines:
        if ln.strip() == '---' or re.match(r'^(title|tags|date|status):', ln):
            continue
        h = HEADING.match(ln)
        if h:
            level = len(h.group(1))
            body.append(f'<h{level}>{html_mod.escape(h.group(2))}</h{level}>')
            continue
        m = CHECK.match(ln)
        if m and m.group(3).strip():
            cls = 'done' if m.group(2).lower() == 'x' else 'open'
            body.append(f'<li class="{cls}">{html_mod.escape(m.group(3))}</li>')
            continue
        if ln.strip():
            body.append(f'<p>{html_mod.escape(ln)}</p>')

    recent = []
    d0 = datetime.date.fromisoformat(date)
    for i in range(7):
        d = (d0 - datetime.timedelta(days=i)).isoformat()
        fp = day_path(d)
        if not os.path.exists(fp):
            continue
        its = scan(read_lines(fp))
        c = sum(1 for _, ok, _ in its if ok)
        recent.append((d, c, len(its)))

    rows = ''.join(
        f'<li><a href="{d}.md">{d}</a> {weekday(d)} · {c}/{t}</li>' for d, c, t in recent)
    page = f'''<!doctype html><meta charset="utf-8"><title>{date} 待办</title>
<style>
:root{{color-scheme:light dark}}
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:780px;margin:40px auto;padding:0 20px;line-height:1.75}}
h1{{font-size:24px;margin:0 0 4px}} h2{{font-size:17px;margin:26px 0 8px}} h3{{font-size:15px;margin:18px 0 6px}}
.bar{{color:#888;margin-bottom:18px;font-size:14px}}
ul{{padding:0}} li{{list-style:none;margin:5px 0;padding-left:26px;position:relative}}
li:before{{content:"☐";position:absolute;left:2px;color:#aaa}}
li.done{{color:#999;text-decoration:line-through}} li.done:before{{content:"☑";color:#2f9e44}}
p{{margin:4px 0;color:#555}} a{{color:inherit}}
aside{{margin-top:44px;padding-top:14px;border-top:1px solid #ddd;font-size:13px;color:#777}}
</style>
<h1>{date} {weekday(date)}</h1>
<div class="bar">完成 {done}/{len(items)}</div>
<ul>{''.join(body)}</ul>
<aside><b>最近 7 天</b><ul>{rows}</ul></aside>'''

    out = os.path.join(ROOT, '.kb', 'dashboard.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(page)
    print(out)
    if open_browser:
        try:
            os.startfile(out)      # noqa: S606
        except Exception:          # noqa: BLE001
            pass


def cmd_open(date):
    p = ensure(date)
    print(p)
    try:
        os.startfile(p)            # noqa: S606
    except Exception:              # noqa: BLE001
        pass


def main():
    ap = argparse.ArgumentParser(description='每日待办与总结')
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('new', 'show', 'close', 'open'):
        sp = sub.add_parser(name)
        sp.add_argument('-d', '--date', default=None)
    sp = sub.add_parser('add')
    sp.add_argument('item')
    sp.add_argument('-d', '--date', default=None)
    sp = sub.add_parser('done')
    sp.add_argument('n', type=int)
    sp.add_argument('-d', '--date', default=None)
    sp = sub.add_parser('html')
    sp.add_argument('-d', '--date', default=None)
    sp.add_argument('--no-open', action='store_true')
    a = ap.parse_args()
    date = a.date or today()

    if a.cmd == 'new':
        cmd_new(date)
    elif a.cmd == 'show':
        cmd_show(date)
    elif a.cmd == 'add':
        cmd_add(date, a.item)
    elif a.cmd == 'done':
        cmd_done(date, a.n)
    elif a.cmd == 'close':
        cmd_close(date)
    elif a.cmd == 'open':
        cmd_open(date)
    elif a.cmd == 'html':
        cmd_html(date, not a.no_open)


if __name__ == '__main__':
    main()
