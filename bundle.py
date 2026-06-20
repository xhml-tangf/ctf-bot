# bundle.py — 拼接器: 将多文件模块合并为单文件, 供在线IDE粘贴
import os

HERE = os.path.dirname(os.path.abspath(__file__))
# 依赖顺序: config → models → bot → team → brain → main (越底层越靠前)
MODULES = ['config', 'models', 'bot', 'team', 'brain', 'main']
LOCAL = set(MODULES) - {'main'}  # 本地模块(拼接时跳过其import行)


def _module_of(stmt: str) -> str:
    """从import语句提取模块名: 'from X import'→X, 'import X'→X"""
    s = stmt.strip()
    if s.startswith('from '):
        return s[len('from '):].split()[0]
    if s.startswith('import '):
        return s[len('import '):].split(',')[0].split(' as ')[0].strip()
    return ''


def _is_import_start(s: str) -> bool:
    """判断是否为import语句的起始行"""
    return s.startswith('import ') or s.startswith('from ')


def bundle(out_name: str = 'ctf_bot_bundled.py') -> str:
    """拼接所有模块: 收集外部import(去重)→拼接类/函数体→输出单文件"""
    imports = []        # 外部import语句(去重)
    seen = set()        # 已收集的import行
    bodies = []         # 所有模块的代码体

    for mod in MODULES:
        path = os.path.join(HERE, mod + '.py')
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        i = 0
        n = len(lines)
        while i < n:
            raw = lines[i]
            s = raw.strip()
            # 跳过空行/注释的import行(实际import从第一个非空非#开始)
            if _is_import_start(s):
                # 处理多行import(含括号续行)
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
                    continue                    # 本地模块import → 跳过
                if full not in seen:
                    seen.add(full)
                    imports.append(full)        # 外部import → 收集
                continue
            bodies.append(raw.rstrip('\n'))     # 普通代码行 → 加入body
            i += 1

    # 输出: 外部import(去重) + 空行 + 所有模块代码体
    out = '\n'.join(imports) + '\n\n\n' + '\n'.join(bodies) + '\n'
    out_path = os.path.join(HERE, out_name)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(out)
    return out_path


if __name__ == '__main__':
    p = bundle()
    print('bundled ->', p)
