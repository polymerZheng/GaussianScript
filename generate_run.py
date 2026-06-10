#!/usr/bin/env python3
"""
generate_run_script.py
扫描当前目录下所有 .gjf 文件，生成 run_all.sh，每行格式：
    g16 <文件名.gjf> 文件名.out
"""

import os

def main():
    gjf_files = sorted([f for f in os.listdir('.') if f.endswith('.gjf')])
    if not gjf_files:
        print("未找到任何 .gjf 文件。")
        return

    with open('run_all.sh', 'w') as sh:
        sh.write("#!/bin/bash\n\n")
        for gjf in gjf_files:
            out = gjf.rsplit('.', 1)[0] + '.out'
            sh.write(f"g16 {gjf} {out}\n")

    # 添加可执行权限（Linux/Mac）
    os.chmod('run_all.sh', 0o755)
    print(f"已生成 run_all.sh，包含 {len(gjf_files)} 条命令。")

if __name__ == "__main__":
    main()
