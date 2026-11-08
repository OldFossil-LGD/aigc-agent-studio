# W3《THE TURN》media hash 证据分册

> **范围**：画布 `fa2c927dfed048a8ac938fe008f4a3c8` 的 `section=media`；不外推到其他作品。  
> **证据状态**：W3 范围内【已验证】全量分页与本地 JSON 复算；通用方法见 `libtv-media-hash-cross.md`。

## 全量闭合

| 项目 | 值 |
|---|---|
| revision | `sha256-54af0b82db1b8952ae8d2a622086f040f5b859cf81e32633ad610fb3c13ac98a` |
| rows / unique mediaId / counts.media | `408 / 408 / 408` |
| type distribution | `image 178 / audio 36 / video 194 / other 0` |
| contentHash present / missing | `206 / 202` |
| unique hash / duplicate groups / extra copies | `189 / 16 / 17` |
| 分页 | `0/200 + 200/200 + 400/8` |

## 三个比例

```text
hash 覆盖率       206/408 = 50.5%
唯一率            189/206 = 91.7%
唯一内容占范围    189/408 = 46.3%
```

【已验证】`image 174/4`、`audio 25/11`、`video 7/187` 是 present/missing 的本作分层；202 个缺失 hash 记录是【不可判定】。

## binding 与来源层边界

【已验证】187 个无 hash video 分为 `bindingStatus=missing 8` 与“有 URL/时长但无 hash 179”。

【已验证】在当前 W3 快照内，`upload-images / sd-gen-save / output` 来源层与 hash 有无完全相关。

【不可判定】平台是否按来源路径决定 `contentHash` 计算；179 个有 URL 无 hash 视频的真实内容、编码与像素质量仍需下载核验。
