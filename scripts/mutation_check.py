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
import json
import shlex
import os
import subprocess

try:
    from . import proc
except ImportError:  # 作为脚本直接运行时
    import proc
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
    # 传 list 就不经过 shell：解释器路径里即便有 & % 空格也不会被解析。
    # 传字符串仍走 shell（兼容旧的单条用法）。
    shell = not isinstance(cmd, (list, tuple))
    r = proc.run(cmd, shell=shell, cwd=cwd, timeout=proc.DEFAULT, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT)
    return r.returncode, r.stdout.decode("utf-8", "replace")


def _failures(output):
    """收集输出里所有失败条目：(kind, 测试标识)。kind 是 FAIL 或 ERROR。

    FAIL = 断言失败（门禁确实判了且判错）；ERROR = 异常提前中断（可能根本没走到断言）。
    归因必须区分这两者，否则"测试里抛了个别的东西"会被当成"门禁抓住了变异"。
    """
    found = []
    for line in (output or "").splitlines():
        for kind in ("FAIL:", "ERROR:"):
            if line.startswith(kind):
                head = line[len(kind):].strip()
                name = head.split(" (")[0].strip().rstrip(".")
                location = head[len(name):].strip()      # 形如 (tests.mod.Class)
                found.append((kind.rstrip(":"), name, location))
    return found


def _first_failure(output):
    found = _failures(output)
    return found[0][1] if found else None


def _is_target(entry, want_kind, want_name, want_in):
    """精确归因：类别、方法名都要相等，给了位置还要位置包含。

    用子串匹配方法名会让 test_target_extra 冒充 test_target。
    """
    kind, name, location = entry
    if kind != want_kind or name != want_name:
        return False
    return (not want_in) or (want_in in location)


def check(file_path, frm, to, test_cmd, expect, cwd, expect_failure=None,
          expect_kind=None, expect_in=None):
    out = []
    original = _read(file_path)
    original_sha = _file_sha(file_path)
    out.append("original sha256 = %s…" % original_sha[:16])

    # 1) 基线必须绿：既要出现期望字样，也要真的退出 0。
    #    只看字样不够——一个报错的运行同样可以打印出 "OK"。
    rc0, o0 = _run(test_cmd, cwd)
    if expect not in o0 or rc0 != 0:
        out.append("[STOP] 基线不绿：%r %s（rc=%d）"
                   % (expect, "出现了" if expect in o0 else "找不到", rc0))
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
        # "抓住"的判据：期望字样消失 + 进程非 0 + **失败确实来自预期的那条测试**。
        # 只凭"字样消失"会把握手失败（导入/语法错误）也算成抓住；
        # 再加上 expect_failure 做正向归因，才能说"红的是它"，而不是"某个东西红了"。
        failures = _failures(o1)
        first = failures[0][1] if failures else None
        broken = [m for m in LOAD_FAILURE_MARKERS if m in o1]
        wanted = (expect_kind or "FAIL").upper()
        if expect_failure is None:
            attributed = True
        else:
            attributed = any(_is_target(entry, wanted, expect_failure, expect_in)
                             for entry in failures)
        caught = expect not in o1 and rc1 != 0 and not broken and attributed
        if broken:
            out.append("[STOP] 变异后测试没跑起来（%s），这次不算捕获" % "、".join(broken))
            out.append(o1[-1500:])
            rc = 3
        elif expect_failure is not None and not attributed:
            out.append("[STOP] 失败归因不符：期望 %r 以断言失败(FAIL)出现，实际失败条目 %r"
                       % (expect_failure, failures[:3] or "无"))
            out.append(o1[-1500:])
            rc = 3
        else:
            out.append("[%s] 变异后 rc=%d，%r %s"
                       % ("OK" if caught else "FAIL", rc1, expect,
                          "已消失且非 0（抓住了）" if caught else "**仍然出现或仍为 0（没抓住）**"))
            if not caught:
                out.append(o1[-1500:])
            rc = 0 if caught else 1
        if caught:
            # 证据必须取自**实际满足判据**的那条，不能按名字随便挑第一条。
            matched = next((entry for entry in failures
                            if expect_failure is None or
                            _is_target(entry, wanted, expect_failure, expect_in)),
                           failures[0] if failures else ("?", first or "?", ""))
            out.append("[证据] %s 失败来自 %s %s"
                       % (matched[0], matched[1], matched[2]))
    finally:
        _write(file_path, original)
        restored = _file_sha(file_path) == original_sha
        out.append("[%s] 还原：**文件字节** sha256 %s"
                   % ("OK" if restored else "FAIL",
                      "与改动前一致" if restored else "**不一致——文件已被污染，请手工恢复**"))
        if not restored:
            out.append("[STOP] 还原失败，请手工恢复该文件")
            # 还原失败必须盖掉"抓住了"：文件已被污染，这次验证不成立。
            rc = 3
    return rc, out


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
        # 门禁报 FAIL 时必须非 0：真实门禁就是这样，"抓住"的判据也依赖退出码。
        _write(gate, "import io,sys\n"
                     "t=io.open('target.py',encoding='utf-8',newline='').read()\n"
                     "ok='GOOD' in t\n"
                     "print('PASS' if ok else 'FAIL')\n"
                     "sys.exit(0 if ok else 1)\n")
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


# 这些字样说明测试压根没加载成功；此时"期望字样消失"不能算门禁抓住了变异。
LOAD_FAILURE_MARKERS = ("SyntaxError", "IndentationError", "ModuleNotFoundError",
                        "ImportError", "failed to import test module", "_FailedTest")


def _quote_executable(path):
    """把解释器路径嵌进**字符串**命令时用；能传 list 就别用这个。

    引号只是缓解，不是保证：Windows 的 cmd 即使加了双引号，%VAR% 仍会展开；
    路径里有 & 时未加引号会被当命令分隔符。所以清单请优先用 list 形式（不经 shell）。
    """
    text = str(path)
    if os.name == "nt":
        return '"%s"' % text.replace('"', '')
    return shlex.quote(text)


def run_cases(path):
    """跑一份用例清单：每条都走 single-case 的同一套判据，最后汇总。

    退出码：任一条没抓住 → 1；否则任一条前提不成立 → 3；全抓住 → 0。
    3 与 0 的区别仍然是"没验到"与"验过了"。
    """
    try:
        with io.open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        print("用例清单读不了：%s" % exc)
        return 2
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        print("用例清单里没有 cases 列表")
        return 2

    codes = []
    for index, case in enumerate(cases, 1):
        if not isinstance(case, dict):
            print("[%02d] 用例格式无效" % index)
            codes.append(2)
            continue
        label = str(case.get("id") or case.get("file") or index)
        missing = [k for k in ("file", "from", "to", "test", "expect") if not case.get(k)]
        if missing:
            print("[%02d] %-34s 缺字段：%s" % (index, label, ",".join(missing)))
            codes.append(2)
            continue
        target = case["file"]
        if not os.path.isfile(target):
            print("[%02d] %-34s 跳过：找不到 %s" % (index, label, target))
            codes.append(3)
            continue
        cwd = case.get("cwd") or os.path.dirname(os.path.abspath(target))
        # {python} 换成当前解释器。list 形式不经过 shell，路径里有 & % 空格都安全；
        # 字符串形式只能靠引号缓解，且 Windows 的 %VAR% 仍会展开——所以优先用 list。
        raw_test = case["test"]
        if isinstance(raw_test, list):
            test_cmd = [sys.executable if str(part) == "{python}" else str(part)
                        for part in raw_test]
        else:
            test_cmd = str(raw_test).replace("{python}", _quote_executable(sys.executable))
        rc, log = check(target, case["from"], case["to"], test_cmd, case["expect"], cwd,
                        expect_failure=case.get("expect_failure"),
                        expect_kind=case.get("expect_kind"),
                        expect_in=case.get("expect_in"))
        verdict = {0: "抓住", 1: "**没抓住**", 3: "前提不成立"}.get(rc, "用法错(%d)" % rc)
        print("[%02d] %-34s %s" % (index, label, verdict))
        # 不论成败都打证据行：成功捕获也要能回看"红的是哪条"。
        evidence = [line for line in (log or []) if str(line).startswith(("[证据]", "[STOP]"))]
        for line in evidence[:1]:
            print("      %s" % str(line)[:160])
        if rc != 0:
            for line in (log or [])[-3:]:
                if str(line).startswith(("[证据]", "[STOP]")):
                    continue
                print("      %s" % str(line)[:160])
        codes.append(rc)

    caught = codes.count(0)
    print("\n共 %d 条：抓住 %d ／ 没抓住 %d ／ 没验到 %d ／ 用法错 %d"
          % (len(codes), caught, codes.count(1), codes.count(3), codes.count(2)))
    if 1 in codes:
        return 1
    if 3 in codes:
        return 3
    if 2 in codes:
        return 2
    return 0


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cases", help="用例清单 JSON：{\"cases\": [{file, from, to, test, expect, cwd?}]}")
    ap.add_argument("--file")
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to", dest="to")
    ap.add_argument("--test")
    ap.add_argument("--expect")
    a, _ = ap.parse_known_args()

    if a.self_test:
        return _self_test()
    if a.cases:
        return run_cases(a.cases)
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
