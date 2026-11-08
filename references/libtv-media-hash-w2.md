# W2《抵达之前》media hash 证据分册

> **范围**：画布 `9acfd4487c9842d985cd9348f6966059` 的 `section=media`；不外推到其他作品。  
> **证据状态**：W2 范围内【已验证】全量分页与本地 JSON 复算；通用方法见 `libtv-media-hash-cross.md`。

## 全量闭合

| 项目 | 值 |
|---|---|
| revision | `sha256-87584b81240ed5775afe6a662d345fe134b2d746980ec6827b8086031ce81ce9` |
| rows / unique mediaId / counts.media | `730 / 730 / 730` |
| type distribution | `image 220 / audio 11 / video 466 / video-clip 33` |
| contentHash present / missing | `129 / 601` |
| unique hash / duplicate groups / extra copies | `83 / 19 / 46` |
| 分页 | `0/200 + 200/100 + 300/100 + 400/100 + 500/100 + 600/200` |

## 三个比例

```text
hash 覆盖率       129/730 = 17.7%
唯一率            83/129  = 64.3%
唯一内容占范围    83/730  = 11.4%
```

【已验证】`video-clip 33` 在四分类中归入 other；`image 119/101`、`audio 7/4`、`video 3/463`、`other 0/33` 是 present/missing 的本作分层。

【已验证】本册取代 `work/media_hashes.tsv` 的 76 行样本口径；旧样本只保留为历史证据，不得再称 W2 全量。

【边界】601 个缺失 hash 记录是【不可判定】，不作唯一或重复判断。
