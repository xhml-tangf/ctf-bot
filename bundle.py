import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = ['config', 'models', 'bot', 'team', 'threats', 'navigator', 'objectives', 'mover', 'brain', 'main']
LOCAL = set(MODULES) - {'main'}


def _module_of(stmt: str) -> str:
    s = stmt.strip()
    if s.startswith('from '):
        return s[len('from '):].split()[0]
    if s.startswith('import '):
        return s[len('import '):].split(',')[0].split(' as ')[0].strip()
    return ''


def _is_import_start(s: str) -> bool:
    return s.startswith('import ') or s.startswith('from ')


def bundle(out_name: str = 'ctf_bot_bundled.py') -> str:
    imports = []
    seen = set()
    bodies = []
    for mod in MODULES:
        path = os.path.join(HERE, mod + '.py')
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        i = 0
        n = len(lines)
        while i < n:
            raw = lines[i]
            s = raw.strip()
            if _is_import_start(s):
                stmt_parts = [s]
                depth = s.count('(') - s.count(')')
                i += 1
                while depth > 0 and i < n:
                    cont = lines[i].strip()
                    stmt_parts.append(cont)
                    depth += cont.count('(') - cont.count(')')
                    i += 1
                full = ' '.join(stmt_parts)
                modname = _module_of(full)
                if modname in LOCAL:
                    continue
                key = full
                if key not in seen:
                    seen.add(key)
                    imports.append(full)
                continue
            bodies.append(raw.rstrip('\n'))
            i += 1
    out = '\n'.join(imports) + '\n\n\n' + '\n'.join(bodies) + '\n'
    out_path = os.path.join(HERE, out_name)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)
    return out_path


if __name__ == '__main__':
    p = bundle()
    print('bundled ->', p)
