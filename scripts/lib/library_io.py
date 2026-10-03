# -*- coding: utf-8 -*-
"""已入库区（data/<品类>/products.json）的写入实现 —— Python 侧。

与 `scripts/lib/library-io.mjs` 是**同一套写入规范**的两个薄实现：
Python 无法 import Node 模块，所以不追求"唯一写入者"，而追求"唯一写入规范"
（见方案 P1-1 / 甲评 §5.2）。三条硬要求：

  1. **序列化规范化**：同一组对象在两侧产出**逐字节相同**的文本。
     跨语言差异有三处，全部钉死（`npm run selftest` 会做双向一致性断言）：
       · 整值浮点 → 整型（`json.dumps(399.0)` 给 '399.0'，`JSON.stringify(399)` 给 '399'）
       · 非 ASCII 不转义（`ensure_ascii=False`，JS 默认输出原文）
       · 紧凑分隔符 `separators=(',', ':')`，键序按解析序保留
       · 已知边界：键名若为纯数字串，JS 会把它们排到最前，Python 不会 —— 本仓库的键
         全是普通标识符，不受影响；NaN/Infinity 两侧行为不同（JS 给 null，Python 给非法 JSON），
         本仓库数据不含这类值。
  2. **写前指纹校验**：载入后若文件被别人改过，立刻抛 `LibraryConflict`，**不做覆盖**。
  3. **文件锁退避重试**：Windows 上批量写会撞共享冲突（`UNKNOWN: unknown error, open ...`），
     这类失败退避重试；**与指纹冲突严格分开，绝不共用重试路径**。

用法：
    import library_io
    lib = library_io.load(path)            # {'products': [...], 'hash': str|None}
    lib['products'].append(item)
    library_io.save(path, lib['products'], expect_hash=lib['hash'])
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

# 库文件当前格式：'compact'（整数组一行）/ 'per-line'（一行一款，便于 git 按行合并）。
# 与 Node 侧 library-io.mjs 的 FORMAT 必须保持一致。
FORMAT = 'per-line'

# 会被退避重试的 errno（文件锁类；不含任何"内容冲突"语义）
#   13=EACCES, 16=EBUSY(git-bash/Linux), 11=EAGAIN, 32/33=Windows 共享冲突
RETRYABLE_ERRNO = {11, 13, 16, 32, 33}


class LibraryConflict(Exception):
    """库文件在载入后被他人修改 —— 拒绝覆盖（不可重试）"""


def _normalize(value):
    """整值浮点归一成整型：与 JS 的 Number 表示对齐，消除跨语言字节漂移"""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def serialize_library(products):
    """规范序列化：唯一允许的库文件文本生成方式"""
    if FORMAT == 'per-line':
        return '[\n' + ',\n'.join(
            json.dumps(_normalize(p), ensure_ascii=False, separators=(',', ':')) for p in products
        ) + '\n]\n'
    return json.dumps(_normalize(products), ensure_ascii=False, separators=(',', ':')) + '\n'


def hash_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def load(path):
    """载入库文件；不存在时返回空数组 + None 指纹（表示"写之前没有基线"）"""
    if not os.path.exists(path):
        return {'products': [], 'hash': None, 'exists': False}
    with open(path, encoding='utf-8') as f:
        text = f.read()
    return {'products': json.loads(text), 'hash': hash_text(text), 'exists': True}


def script_actor():
    """批量写库脚本的操作者名（留痕用）：FLOW_ACTOR 优先，否则取脚本文件名。

    只给**批量工具**用（见 save 的 actor 参数说明）。
    """
    return os.environ.get('FLOW_ACTOR') or os.path.basename(sys.argv[0] or '') or 'unknown'


def _journal_batch_write(path, products, actor):
    """批量写库留痕（方案 P1-1 第三要素）：一次写入记一条，不逐产品。

    为什么必须有：批量工具重写整品类（如 classify-facets 一次 517 条）时，
    产品级流转日志里一条记录都没有 —— `flow:log` 出现盲区，只能说"git log 兜底"，
    而 git log 说不出「谁在什么时候用哪个脚本改了哪一品类的多少条」。
    """
    try:
        journal = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(path))), '_flow', 'journal.jsonl'
        )
        cat = os.path.basename(os.path.dirname(path))
        os.makedirs(os.path.dirname(journal), exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
        entry = {'ts': ts, 'actor': actor, 'action': 'batch-write',
                 'key': '%s/products.json' % cat, 'count': len(products)}
        with open(journal, 'a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(',', ':')) + '\n')
    except OSError:
        # 留痕失败不影响写入本身（写入已经成功），但要让调用者看见
        sys.stderr.write('⚠ 写库留痕失败（数据已写入）：%s\n' % path)


def save(path, products, expect_hash=None, retries=5, actor=None):
    """写入库文件。

    两类失败严格分开：指纹不一致 → 抛 LibraryConflict（立刻失败、不重试）；
    文件锁类 OSError → 有限次退避重试。共用重试路径会让守卫被重试架空。

    actor：**批量工具必须传**（用 script_actor()）→ 写入成功后向 journal 追加一条
      `batch-write` 粗粒度留痕。flow:* 流转不传（它自己有 publish/recall 等条目）。
    """
    text = serialize_library(products)

    current = hash_text(open(path, encoding='utf-8').read()) if os.path.exists(path) else None
    if current != expect_hash:
        raise LibraryConflict(
            '库文件已被他人修改，拒绝覆盖：%s\n'
            '  载入时指纹：%s\n  磁盘现指纹：%s\n'
            '  同一品类的写入必须串行：请重新载入（重跑命令）后再试。'
            % (path, expect_hash or '（文件不存在）', current or '（文件不存在）')
        )

    last = None
    for i in range(retries + 1):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
            if actor:
                _journal_batch_write(path, products, actor)
            return text
        except OSError as e:
            errno = e.errno or getattr(e, 'winerror', None) or 0
            if errno not in RETRYABLE_ERRNO:
                raise
            last = e
            if i < retries:
                time.sleep(0.04 * (2 ** i))
    # retries >= 0 时循环至少执行一次，故 last 必已被赋值为某个 OSError
    assert last is not None, 'retries >= 0 时循环必然执行，last 不会被跳过'
    raise last


def save_products(path, mutate, actor=None):
    """便捷封装：载入 → 交给 mutate(products) 改 → 带指纹写回。

    典型用法（把"读-改-写"三步收敛到一处，避免各处自己重复实现而漏掉守卫）：
        library_io.save_products(pp, lambda ps: ps.append(new_item), actor=script_actor())
    """
    lib = load(path)
    mutate(lib['products'])
    return save(path, lib['products'], expect_hash=lib['hash'], actor=actor)


if __name__ == '__main__':
    # 手工自检：把 stdin 的 JSON 规范化后打到 stdout（供跨语言一致性对比）
    #
    # stdin 也必须重配编码：Windows 上 sys.stdin 默认跟随控制台代码页（cp936/gbk），
    # 管道喂进来的 UTF-8 字节会被按错误编码解码，产生代理对字符
    # （UnicodeEncodeError: surrogates not allowed）。只配 stdout 不够。
    # newline='\n' 是必须的：否则 Windows 上会把 \n 翻成 \r\n，跨语言字节比对会假失败
    for _stream in (sys.stdin, sys.stdout):
        try:
            _stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    sys.stdout.reconfigure(encoding='utf-8', newline='\n')
    sys.stdout.write(serialize_library(json.loads(sys.stdin.buffer.read().decode('utf-8'))))
