#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mutation_check —— **验证验证器**：给一处源码打一个已知的"坏改动"，
跑门禁，看它**有没有红**。红了＝门禁真的在查这件事；没红＝门禁是空壳。

为什么要有它（2026-10-16 立）：
  本库已连撞三次"门禁自己的判据是缺陷"（豁免表写成 0 册命中的后缀 ·
  工位检查里一个从来不存在的册名 · 跨册重复的分类少一桶）。
  三次都是**门禁在报，但报的理由是错的**。变异检验是唯一能把这类问题
  逼出来的动作——**它不问你写了什么判据，只问"改坏了，你红不红"。**

用法（**只改一个文件、跑一条命令、必定还原**）：

  python3 scripts/mutation_check.py \
    --file scripts/libtv_orchestrate.py \
    --from "budget_lo = budget_hi = total" \
    --to   "budget_lo = budget_hi = 0" \
    --test "python3 scripts/libtv_orchestrate.py --self-test" \
    --expect "自检：142 通过 / 0 失败"

判据（**四条，缺一条结论就不成立**）：
  1. **改动真的落盘了**——替换后重新读文件、确认文本确实变了（**不是"我以为我改了"**）；
  2. **跑之前基线是绿的**——先跑一次未变异的命令，基线不绿就没有对照可言；
  3. **变异后转红**——`--expect` 给的是**未变异时应该出现的字样**，
     变异后它**不该再出现**；它消失了＝被抓住；
  4. **无论如何都还原**——`try/finally` 还原并**复算 SHA-256**，确认与改动前逐字节相同。

退出码：0 变异被抓住 ｜ 1 变异没被抓住（门禁是空壳） ｜ 2 用法错 ｜ 3 前提不成立
        （文件没变 / 基线不绿 / 还原失败）——**3 与 0 的区别是"没验到"与"验过了"。**

★★★ 2026-10-16 首跑即抓到自己的一个真 bug（**记在这里，因为它是本工具存在的理由**）：
  第一版用 `io.open(p, encoding="utf-8")` **文本模式**读写——Windows 上会把 `\n` 写成 `\r\n`。
  于是**还原之后文件的字节变了**（`libtv_orchestrate.py` 从全 LF 变成全 CRLF，
  SHA-256 由 `1bc2003094…` 变成 `87d92d1678…`），**而工具自己却报"还原：与改动前一致"**
  ——因为它算的是**解码后文本**的哈希，不是**文件字节**的哈希。
  **⟹ 两条修法（已落）**：① 读写一律 `newline=""`（不翻译行尾）；
  ② **还原校验改成"原始字节的 SHA-256"**，不再是文本哈希。
  **教训与本库既有纪律同形**：**"我核对过了"必须核对的是同一个对象**——
  拿文本哈希去证"文件没变"，和拿退出码去证"对照组成立"是同一类错误。
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys


def _read(p):
    # ★ newline="" —— **不翻译行尾**。少了这个参数，Windows 上写回会把 \n 变 \r\n，
    #   文件字节就变了（2026-10-16 实测：首跑即踩，见文件头）。
    with io.open(p, encoding="utf-8", newline="") as f:
        return f.read()


def _write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(s)


def _file_sha(p):
    """**文件字节**的 SHA-256——还原校验必须用它，不能用文本哈希。"""
    with io.open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _run(cmd, cwd):
    r = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def check(file_path, frm, to, test_cmd, expect, cwd):
    out = []
    original = _read(file_path)
    original_sha = _file_sha(file_path)
    out.append("original sha256 = %s…" % original_sha[:16])

    # 1) 基线必须绿
    rc0, o0 = _run(test_cmd, cwd)
    if expect not in o0:
        out.append("[STOP] 基线不绿：未变异的输出里找不到 %r（rc=%d）" % (expect, rc0))
        out.append(o0[-1500:])
        return 3, out
    out.append("[OK]   基线绿：未变异时出现了 %r" % expect)

    mutated = None
    try:
        hits = original.count(frm)
        if hits != 1:
            out.append("[STOP] 锚点命中 %d 次（要求恰好 1 次）——先修锚点再谈变异" % hits)
            return 3, out
        mutated = original.replace(frm, to)
        # 1) 改动真的落盘了
        _write(file_path, mutated)
        if _read(file_path) == original:
            out.append("[STOP] 写进去了但内容没变——等于没变异（这一步就是防'我以为我改了'）")
            return 3, out
        out.append("[OK]   变异已落盘：%d → %d 字符" % (len(original), len(mutated)))

        rc1, o1 = _run(test_cmd, cwd)
        caught = expect not in o1
        out.append("[%s] 变异后 rc=%d，%r %s"
                   % ("OK" if caught else "FAIL", rc1, expect,
                      "已消失（抓住了）" if caught else "**仍然出现（没抓住）**"))
        if not caught:
            out.append(o1[-1500:])
        return (0 if caught else 1), out
    finally:
        _write(file_path, original)
        restored = _file_sha(file_path) == original_sha
        out.append("[%s] 还原：**文件字节** sha256 %s"
                   % ("OK" if restored else "FAIL",
                      "与改动前一致" if restored else "**不一致——文件已被污染，请手工恢复**"))
        if not restored:
            out.append("[STOP] 还原失败，请手工恢复该文件")


def _self_test():
    """用一个临时文件验"工具本身"：四种情形各跑一次。"""
    import tempfile
    ok = bad = 0

    def case(name, cond):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  [OK]   %s" % name)
        else:
            bad += 1
            print("  [NG]   %s" % name)

    d = tempfile.mkdtemp()
    try:
        target = os.path.join(d, "target.py")
        # 一个"门禁"：文件里含 GOOD 就打印 PASS
        gate = os.path.join(d, "gate.py")
        # ★ 自检自己写文件也要 newline=""——否则 Windows 上写出来是 CRLF，
        #   而 _read 用 newline="" 读回的是原样，两边对不上（2026-10-16 实测踩到）。
        _write(gate, "import io,sys\n"
                     "t=io.open('target.py',encoding='utf-8',newline='').read()\n"
                     "print('PASS' if 'GOOD' in t else 'FAIL')\n")
        _write(target, "GOOD = 1\n")
        cmd = "%s %s" % (sys.executable, gate)

        # ① 把 GOOD 改成 BAD → 门禁应变红 → 抓得住
        rc, out = check(target, "GOOD = 1", "BAD = 1", cmd, "PASS", d)
        case("变异被抓住 → rc=0", rc == 0)
        case("变异后已还原", _read(target) == "GOOD = 1\n")

        # ② 锚点不存在 → 前提不成立 → rc=3（不是"通过"）
        rc, out = check(target, "NOPE = 1", "BAD = 1", cmd, "PASS", d)
        case("锚点不存在 → rc=3", rc == 3)

        # ③ 换成一个门禁根本不管的改动 → 抓不住 → rc=1
        _write(target, "GOOD = 1\nOTHER = 2\n")
        rc, out = check(target, "OTHER = 2", "OTHER = 3", cmd, "PASS", d)
        case("门禁不管的改动 → 抓不住 → rc=1", rc == 1)
        case("抓不住时也已还原", "OTHER = 2" in _read(target))

        # ④ 基线本身就不绿 → rc=3
        _write(target, "BAD = 1\n")
        rc, out = check(target, "BAD = 1", "GOOD = 1", cmd, "PASS", d)
        case("基线不绿 → rc=3", rc == 3)
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    print("自检：%d 通过 / %d 失败" % (ok, bad))
    return 0 if bad == 0 else 1


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--file")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to", dest="to")
    ap.add_argument("--test")
    ap.add_argument("--expect")
    a, _ = ap.parse_known_args()

    if a.self_test:
        return _self_test()
    if not (a.file and a.frm and a.to and a.test and a.expect):
        print(__doc__)
        return 2
    if not os.path.isfile(a.file):
        print("找不到文件：%s" % a.file)
        return 2
    cwd = os.path.dirname(os.path.abspath(a.file))
    rc, out = check(a.file, a.frm, a.to, a.test, a.expect, cwd)
    print("\n".join(out))
    print("\n结论：%s" % {0: "变异被抓住（门禁真的在查这件事）",
                        1: "**变异没被抓住——门禁是空壳**",
                        3: "**前提不成立，没验到**（≠ 通过）"}.get(rc, "未知"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
