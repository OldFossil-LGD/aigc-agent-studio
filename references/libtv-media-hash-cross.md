# LibTV media hash 跨作方法册

> **何时读**：统计 `section=media` 的 `contentHash`、做三作 hash 对照、解释 hash 缺失或重复时。  
> **读完回哪**：`libtv-canvas-nodes.md` 的生产快照入口；三作范围分别读 `libtv-media-hash-w1.md`、`libtv-media-hash-w2.md`、`libtv-media-hash-w3.md`。  
> **证据状态**：本册只收已有【已验证】方法；单作数字不升格为通用规则。

## 跨作规则

| 编号 | 【已验证】规则 |
|---|---|
| `R-HASH-COV-1` | hash 覆盖率、唯一率、唯一内容占范围必须分别报告，并写明分母：`present/total`、`unique/present`、`unique/total`。 |
| `R-HASH-COMP-1` | 不同 revision、范围、字段源或类型构成的 hash 数字不得横向比较绝对数量，也不得据此排名作品优劣。 |
| `R-HASH-UNK-1` | 缺 `contentHash` 是【不可判定】：不归入唯一、重复或缺媒体。 |
| `R-HASH-DEL-1` | hash 相同不能删除节点；节点身份按 `nodeKey`，内容同一性才按 hash。 |

## 媒体存在与 hash 覆盖

| 编号 | 【已验证】规则 |
|---|---|
| `M22` | `bindingStatus`/URL/时长与 `contentHash` 回答不同问题；先分“无媒体”与“有媒体但无 hash”，再谈 hash 覆盖。 |
| `M23` | hash 缺失归因必须联 `mediaPersistence`、节点 action/model 与字段向量；task 状态和 identity 状态只能作分层变量。 |
| `M24` | 来源路径与 hash 的完全相关只写相关性；没有 schema、任务日志或平台答复时，平台根因是【不可判定】。 |
| `M25` | 缺失字段按列报告，不能把缺 hash、缺 mimeType、缺 byteSize 概括成一个“元数据缺失”。 |

## 执行顺序

```text
section=media 分页并锁 revision
  -> rows / unique mediaId / type distribution 闭合
  -> 统计 contentHash present / missing
  -> 分别计算三个比例
  -> 缺 hash 标【不可判定】
  -> 需要归因时再联 binding 与字段向量
```

**边界**：媒体解码、像素质量、真实内容去重和平台计算根因不在本册判定范围；未获用户批准不得下载媒体。
