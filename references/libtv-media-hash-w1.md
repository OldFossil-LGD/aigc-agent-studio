# W1《弥寿计划》media hash 证据分册

> **范围**：画布 `9b28eb33680f4f63ab78ad747b2eed5c` 的 `section=media`；不外推到其他作品。  
> **证据状态**：W1 范围内【已验证】全量分页与本地 JSON 复算；通用方法见 `libtv-media-hash-cross.md`。

## 全量闭合

| 项目 | 值 |
|---|---|
| revision | `sha256-fa8dabf7218bc342f18c434233b78bdc041961f0d7493a4e423bc9bf9167b30c` |
| rows / unique mediaId / counts.media | `160 / 160 / 160` |
| type distribution | `image 42 / audio 0 / video 118 / other 0` |
| contentHash present / missing | `36 / 124` |
| unique hash / duplicate groups / extra copies | `36 / 0 / 0` |
| 分页 | `offset=0, limit=200, total=160, itemCount=160, nextOffset=null` |

## 三个比例

```text
hash 覆盖率       36/160 = 22.5%
唯一率            36/36  = 100.0%
唯一内容占范围    36/160 = 22.5%
```

【已验证】`image 33/9`、`video 3/115` 是 present/missing 的本作分层；124 个缺失 hash 记录是【不可判定】，不作唯一或重复判断。

【边界】W1 的 3 个被引用 audio 不在本画布 `section=media` 节点集合内；不能把引用素材补进 160 项分母。
