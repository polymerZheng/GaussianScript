#!/usr/bin/env python3
"""
parse_g16_out.py  (最终版：修复赝势定义 + 路由#号 + 空行)
用法: python parse_g16_out.py <gaussian_output.out>
"""

import re
import sys
import os
from collections import OrderedDict

# ========== 可修改的计算资源 ==========
NPROC = 6
MEM   = "12GB"
# =====================================

# ---------- 元素周期表 ----------
ATOMIC_NUMBER_TO_SYMBOL = {
    1: "H", 2: "He", 3: "Li", 4: "Be", 5: "B", 6: "C", 7: "N", 8: "O", 9: "F", 10: "Ne",
    11: "Na", 12: "Mg", 13: "Al", 14: "Si", 15: "P", 16: "S", 17: "Cl", 18: "Ar",
    19: "K", 20: "Ca", 21: "Sc", 22: "Ti", 23: "V", 24: "Cr", 25: "Mn", 26: "Fe",
    27: "Co", 28: "Ni", 29: "Cu", 30: "Zn", 31: "Ga", 32: "Ge", 33: "As", 34: "Se",
    35: "Br", 36: "Kr", 37: "Rb", 38: "Sr", 39: "Y", 40: "Zr", 41: "Nb", 42: "Mo",
    43: "Tc", 44: "Ru", 45: "Rh", 46: "Pd", 47: "Ag", 48: "Cd", 49: "In", 50: "Sn",
    51: "Sb", 52: "Te", 53: "I", 54: "Xe", 55: "Cs", 56: "Ba", 57: "La", 58: "Ce",
    59: "Pr", 60: "Nd", 61: "Pm", 62: "Sm", 63: "Eu", 64: "Gd", 65: "Tb", 66: "Dy",
    67: "Ho", 68: "Er", 69: "Tm", 70: "Yb", 71: "Lu", 72: "Hf", 73: "Ta", 74: "W",
    75: "Re", 76: "Os", 77: "Ir", 78: "Pt", 79: "Au", 80: "Hg", 81: "Tl", 82: "Pb",
    83: "Bi", 84: "Po", 85: "At", 86: "Rn", 87: "Fr", 88: "Ra", 89: "Ac", 90: "Th",
    91: "Pa", 92: "U", 93: "Np", 94: "Pu", 95: "Am", 96: "Cm", 97: "Bk", 98: "Cf",
    99: "Es", 100: "Fm", 101: "Md", 102: "No", 103: "Lr", 104: "Rf", 105: "Db",
    106: "Sg", 107: "Bh", 108: "Hs", 109: "Mt", 110: "Ds", 111: "Rg", 112: "Cn",
    113: "Nh", 114: "Fl", 115: "Mc", 116: "Lv", 117: "Ts", 118: "Og"
}

SYMBOL_TO_NUMBER = {v: k for k, v in ATOMIC_NUMBER_TO_SYMBOL.items()}

def atomic_symbol(num):
    return ATOMIC_NUMBER_TO_SYMBOL.get(num, "X")

def atomic_number(sym):
    return SYMBOL_TO_NUMBER.get(sym, 0)

# ---------- 路由提取（从 gjf，支持多行）----------
def extract_route_from_gjf(gjf_path):
    with open(gjf_path, 'r') as f:
        lines = f.readlines()
    route_lines = []
    in_route = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            in_route = True
            route_content = re.sub(r'^#\s*', '', stripped)
            route_lines.append(route_content)
        elif in_route:
            if stripped == "":
                break
            else:
                route_lines.append(stripped)
    if not route_lines:
        raise ValueError(f"在 {gjf_path} 中未找到路由行。")
    return " ".join(route_lines)

# ---------- 从输出文件提取路由（备用）----------
def extract_route_section(lines):
    route_lines = []
    in_route = False
    for line in lines:
        if line.startswith(" #"):
            in_route = True
            route_lines.append(line.strip())
        elif in_route:
            break
    if not route_lines:
        raise ValueError("未找到路由行（以 ' #' 开头）。")
    return " ".join(route_lines)

# ---------- 电荷/自旋 ----------
def extract_charge_mult(full_text):
    m = re.search(r'Charge\s*=\s*([+-]?\d+)\s*Multiplicity\s*=\s*(\d+)', full_text)
    if not m:
        raise ValueError("未找到 'Charge = ... Multiplicity = ...' 行。")
    return int(m.group(1)), int(m.group(2))

# ---------- 坐标提取（最后优化结构）----------
def extract_coordinates(lines, full_text):
    coord_re = re.compile(
        r'^\s*(\d+)\s+(\d+)\s+.*?([-+]?\d+\.\d{6,})\s+([-+]?\d+\.\d{6,})\s+([-+]?\d+\.\d{6,})'
    )

    def find_last_block(label):
        last_coords = None
        capture = False
        current_coords = []
        for line in lines:
            if label in line:
                capture = True
                current_coords = []
                continue
            if capture:
                if line.strip() == "":
                    if current_coords:
                        last_coords = current_coords
                        current_coords = []
                        capture = False
                    continue
                m = coord_re.match(line)
                if m:
                    an = int(m.group(2))
                    x = float(m.group(3))
                    y = float(m.group(4))
                    z = float(m.group(5))
                    current_coords.append((atomic_symbol(an), x, y, z))
                else:
                    if current_coords:
                        last_coords = current_coords
                        current_coords = []
                        capture = False
        if current_coords:
            last_coords = current_coords
        return last_coords

    for label in ["Input orientation:", "Standard orientation:"]:
        coords = find_last_block(label)
        if coords:
            return coords
    raise ValueError("未找到坐标表格，请检查输出文件。")

# ---------- 判断是否含重原子 ----------
def has_heavy_atoms(coords):
    for sym, _, _, _ in coords:
        if atomic_number(sym) > 18:
            return True
    return False

# ---------- 从输出文本提取基组名称 ----------
def get_basis_from_out(full_text):
    m = re.search(r'Standard basis:\s*(\S+)', full_text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    m = re.search(r'Basis set:\s*(\S+)', full_text, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    return None

# ---------- 读取原始 gjf 的完整基组文本 ----------
def read_gjf_basis_text(gjf_path):
    with open(gjf_path, 'r') as f:
        lines = f.readlines()

    charge_mult_pat = re.compile(r'^\s*([+-]?\d+)\s+(\d+)\s*$')
    coord_pat = re.compile(r'^\s*([A-Z][a-z]?)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s+([-+]?\d+\.\d+)\s*$')

    state = 'start'
    coord_count = 0
    basis_start = None
    for i, line in enumerate(lines):
        if state == 'start':
            if charge_mult_pat.match(line):
                state = 'coords'
                continue
        elif state == 'coords':
            m = coord_pat.match(line)
            if m:
                coord_count += 1
                continue
            elif line.strip() == '':
                continue
            else:
                basis_start = i
                break
    if basis_start is None:
        return ""
    return "".join(lines[basis_start:])

# ---------- 替换轻元素基组为 6-31G* ----------
def replace_light_basis(basis_text, coords):
    light_syms = set()
    for sym, _, _, _ in coords:
        if atomic_number(sym) <= 18:
            light_syms.add(sym)

    if not light_syms:
        return basis_text

    elem_list_pat = re.compile(r'^(\s*(?:[A-Z][a-z]?\s+)+)0\s*$', re.MULTILINE)
    lines = basis_text.splitlines(True)
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = elem_list_pat.match(line)
        if m:
            elems_str = m.group(1).strip()
            elems = elems_str.split()
            if any(atomic_number(e) > 18 for e in elems):
                new_lines.append(line)
            else:
                new_lines.append(line)
                if i + 1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line != '****':
                        new_lines.append("6-31G*\n")
                        i += 1
        else:
            new_lines.append(line)
        i += 1
    return "".join(new_lines)

# ---------- 路由清理 ----------
def clean_route(route_str):
    route_str = re.sub(r'\bscrf\s*(?:=\s*)?(?:\([^)]*\)|\S+)', '', route_str, flags=re.IGNORECASE)
    route_str = re.sub(r'\bopt\b(?:=(?:\([^)]*\)|\S+))?', '', route_str, flags=re.IGNORECASE)
    route_str = re.sub(r'\bfreq\b(?:=(?:\([^)]*\)|\S+))?', '', route_str, flags=re.IGNORECASE)
    route_str = re.sub(r'\s+', ' ', route_str).strip()
    return route_str

def extract_scrf(route_str):
    m = re.search(r'\bscrf\s*(?:=\s*)?(?:\([^)]*\)|\S+)', route_str, re.IGNORECASE)
    return m.group(0) if m else ""

# ---------- 写入 gjf ----------
def write_gjf(filename, route, title, charge, mult, coords, basis_text=""):
    # 将 #p 或 # p 替换为 #
    route = re.sub(r'#\s*p', '#', route, count=1)
    with open(filename, 'w') as f:
        f.write(f"%nprocshared={NPROC}\n")
        f.write(f"%mem={MEM}\n")
        if not route.startswith("#"):
            route = "# " + route
        f.write(f"{route}\n")
        f.write("\n")
        f.write(f"{title}\n")
        f.write("\n")
        f.write(f"{charge} {mult}\n")
        for sym, x, y, z in coords:
            f.write(f" {sym:<2s}  {x:14.8f}  {y:14.8f}  {z:14.8f}\n")
        if basis_text.strip():
            f.write("\n")           # 坐标后空行
            f.write(basis_text)
            if not basis_text.endswith('\n'):
                f.write('\n')
        f.write("\n")               # 文件末尾空行

# ---------- 主程序 ----------
def main():
    if len(sys.argv) != 2:
        print(f"用法: {sys.argv[0]} <gaussian_output.out>")
        sys.exit(1)

    out_path = sys.argv[1]
    if not os.path.isfile(out_path):
        print(f"错误: 文件 '{out_path}' 不存在。")
        sys.exit(1)

    with open(out_path, 'r') as f:
        lines = f.readlines()
        full_text = "".join(lines)

    basename = os.path.splitext(out_path)[0]
    gjf_original = basename + ".gjf"

    if os.path.exists(gjf_original):
        try:
            route_str = extract_route_from_gjf(gjf_original)
        except Exception:
            route_str = extract_route_section(lines)
    else:
        route_str = extract_route_section(lines)

    charge, mult = extract_charge_mult(full_text)
    coords = extract_coordinates(lines, full_text)
    scrf_part = extract_scrf(route_str)

    # 轻元素体系
    if not has_heavy_atoms(coords):
        route1 = clean_route(route_str)
        write_gjf(f"{basename}_preciseEnergy.gjf",
                  route1 if route1 else "#p",
                  "precise energy", charge, mult, coords)

        route2 = "#p M052X/6-31G*"
        if scrf_part:
            route2 += f" {scrf_part}"
        write_gjf(f"{basename}_solvent.gjf", route2, "solvent sp", charge, mult, coords)
        write_gjf(f"{basename}_vacuum.gjf", "#p M052X/6-31G*", "vacuum sp", charge, mult, coords)
        print("已生成（轻元素体系）：")
        print(f"  {basename}_preciseEnergy.gjf")
        print(f"  {basename}_solvent.gjf")
        print(f"  {basename}_vacuum.gjf")
        return

    # 重元素处理
    basis_name = get_basis_from_out(full_text)
    if not basis_name:
        m = re.search(r'/(\S+)', route_str)
        if m:
            basis_name = m.group(1).lower()
        else:
            raise ValueError("无法确定基组类型")

    if "genecp" in basis_name:
        if not os.path.exists(gjf_original):
            raise FileNotFoundError(f"未找到原始输入文件 {gjf_original}，无法获取基组信息")
        original_basis_text = read_gjf_basis_text(gjf_original)

        # preciseEnergy
        route1 = clean_route(route_str)
        write_gjf(f"{basename}_preciseEnergy.gjf",
                  route1 if route1 else "#p",
                  "precise energy", charge, mult, coords,
                  basis_text=original_basis_text)

        # solvent / vacuum
        modified_basis = replace_light_basis(original_basis_text, coords)
        route2 = "#p M052X/genecp"
        if scrf_part:
            route2 += f" {scrf_part}"
        write_gjf(f"{basename}_solvent.gjf", route2, "solvent sp", charge, mult, coords,
                  basis_text=modified_basis)
        write_gjf(f"{basename}_vacuum.gjf", "#p M052X/genecp", "vacuum sp", charge, mult, coords,
                  basis_text=modified_basis)

    else:
        # 自带赝势基组
        route1 = clean_route(route_str)
        write_gjf(f"{basename}_preciseEnergy.gjf",
                  route1 if route1 else "#p",
                  "precise energy", charge, mult, coords)

        # 生成 solvent/vacuum 基组和赝势块
        light_syms = sorted(set(sym for sym,_,_,_ in coords if atomic_number(sym) <= 18))
        heavy_syms = sorted(set(sym for sym,_,_,_ in coords if atomic_number(sym) > 18))
        basis_lines = []
        if light_syms:
            basis_lines.append(f"{' '.join(light_syms)} 0")
            basis_lines.append("6-31G*")
            basis_lines.append("****")
        if heavy_syms:
            basis_lines.append(f"{' '.join(heavy_syms)} 0")
            basis_lines.append(basis_name)   # 基组定义
            basis_lines.append("****")
            basis_lines.append("")           # 空行
            basis_lines.append(f"{' '.join(heavy_syms)} 0")
            basis_lines.append(basis_name)   # 赝势定义
        modified_basis = "\n".join(basis_lines) + "\n"

        route2 = "#p M052X/genecp"
        if scrf_part:
            route2 += f" {scrf_part}"
        write_gjf(f"{basename}_solvent.gjf", route2, "solvent sp", charge, mult, coords,
                  basis_text=modified_basis)
        write_gjf(f"{basename}_vacuum.gjf", "#p M052X/genecp", "vacuum sp", charge, mult, coords,
                  basis_text=modified_basis)

    print("成功生成（重元素体系）:")
    print(f"  {basename}_preciseEnergy.gjf")
    print(f"  {basename}_solvent.gjf")
    print(f"  {basename}_vacuum.gjf")

if __name__ == "__main__":
    main()
