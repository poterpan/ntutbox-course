import re, json, datetime as dt

def unfold(text):
    # RFC5545 line unfolding: a line starting with space/tab continues previous
    text = text.replace('\r\n', '\n')
    out = []
    for line in text.split('\n'):
        if line[:1] in (' ', '\t') and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out

def parse(path):
    lines = unfold(open(path, encoding='utf-8').read())
    cal_props = {}
    events = []
    cur = None
    for ln in lines:
        if ln == 'BEGIN:VEVENT':
            cur = {}
            continue
        if ln == 'END:VEVENT':
            events.append(cur); cur = None; continue
        if ':' not in ln:
            continue
        name_part, value = ln.split(':', 1)
        bits = name_part.split(';')
        name = bits[0]
        params = {}
        for p in bits[1:]:
            if '=' in p:
                k, v = p.split('=', 1); params[k] = v
        if cur is None:
            if name not in ('BEGIN', 'END'):
                cal_props.setdefault(name, []).append(value)
        else:
            cur.setdefault(name, []).append((params, value))
    return cal_props, events

def first(ev, key):
    v = ev.get(key)
    return v[0][1] if v else None

def params_of(ev, key):
    v = ev.get(key)
    return v[0][0] if v else {}

def to_date(s):
    # returns (date, is_all_day)
    if re.fullmatch(r'\d{8}', s):
        return dt.date(int(s[0:4]), int(s[4:6]), int(s[6:8])), True
    m = re.fullmatch(r'(\d{8})T(\d{6})Z?', s)
    if m:
        d = m.group(1)
        return dt.date(int(d[0:4]), int(d[4:6]), int(d[6:8])), False
    return None, False
