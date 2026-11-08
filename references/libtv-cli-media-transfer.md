# LibTV CLI 媒体上下行：`upload` 实现与 `download` 实现

> **来源**：恢复载荷 `libtv-pkg-runtime.js`（REA 静态 · 2026-10-15/16）。
> **为什么单列**：**上行（`upload`）与下行（`download`）的参数不是一套**，且都与网页端不同；
> 而"交付/进料"两侧此前只有命令面、没有实现层。
> **读完回哪**：`libtv-quality-delivery-content.md` §七（下载/导出实现）· `libtv-cli-env-binding.md`（CLI 环境与绑定）。

---

## 一、★ 先记这条：**CLI 与网页的上传参数不是一套**

| 参数 | **CLI** | 网页端 |
|---|---|---|
| 分片大小 | **5 MiB**（`BRIDGE_DEFAULT_PART_SIZE`） | **1 MiB**（`modelUploadPartSize`） |
| 超时 | **2 分钟**（`BRIDGE_UPLOAD_TIMEOUT_MS = 120000`） | **10 分钟**（`modelUploadTimeout = 600000`） |

**→ 讨论"上传上限/超时"必须先说是哪一侧。** **各类"大小/数量"上限的集中表见 `libtv-client-limits.md`。**

## 二、两次预签名调用（逐字）

```text
POST ${bridgeApiHost}/gateway/oss-server-api/oss-service/api/oss/pre-sign/multipart/init/4
headers: { Token: <token>, Content-Type: application/json, ...CLI 客户端头 }
body:    { path, fileSize, partSize }
→ 必须返回 data.uploadId 与 data.parts[]，否则 `initMultipartUpload: 响应无效`

POST ${bridgeApiHost}/…/multipart/complete/4
body:    { path, uploadId }
→ 必须返回 data.path，否则 `completeMultipartUpload: 响应无效`
```

- **鉴权头是 `Token`**（不是 `Authorization`）；**bizCode 字面量 `"4"` 拼在路径末尾**；
- `code !== undefined && code !== 0` → 抛 `msg ?? "<函数名> 失败 [code]"`；
- **bridgeApiHost 未配置** → `config.tv.bridgeApiHost 未配置，无法走预签名上传`。

## 三、★★ 对象键是**按内容寻址**（天然去重）

```text
path = `upload-images/${userUuid}/${sha1(buffer)}${原扩展名}`
返回  { path, url, sha1Hex }
```

**同内容同用户 → 同 key**；**`sha1Hex` 会回给调用方** ⟹ **可做本地↔远端同一性核对**。

## 四、分片上传是**串行**的（不要以为会并发）

```text
for i in 0..parts-1:   chunk = buffer[i*5MiB : min((i+1)*5MiB, size)]
   fetch(part.url, { method: part.method || "PUT", body: chunk, 每片独立 120s 超时 })
   !ok → `分片 ${partNumber} 上传失败 HTTP ${status}: ${text前120}`
   进度：completed/total，最后 onProgress(1)
完成后取 URL：completeResult.cdnUrl || completeResult.ossUrl || completeResult.path
  三者皆空 → `上传完成但未返回有效 URL`
```

**★ 分片 URL 与 method 由 init 响应给出**——**不要自己拼 OSS URL**；**每片各自超时**。

## 五、媒体类型推断与**一处不一致**

`EXT_TO_KIND`（18 个）：**image** = png·jpg·jpeg·webp·gif·bmp·svg ；
**video** = mp4·mov·webm·mkv·**avi** ；**audio** = mp3·wav·aac·m4a·flac·ogg 。

- **显式 `-t image|video|audio` 优先**，否则按扩展名推断，都不命中 → `null`；
- **MIME 表只有 17 条——`avi` 不在其中** ⟹ **`.avi` 会被猜成 `video/mp4`**（容器与实际不符；
  **服务端是否接受未验证**）；
- 扩展名缺失或不识别 → 按类兜底 `image/jpeg` / `video/mp4` / `audio/mpeg`。

**节点名**：`getNodeNameFromFileName` ＝ 文件名去最后一个扩展名（**只在最后一个点不是首位时切**，
`.env` 这类前导点文件名不受影响）；空名 → `undefined`。

## 六、下行：`download` 实现（要点，全文见 `libtv-quality-delivery-content.md` §七）

- **下载分组＝递归展开组内叶子**；三条逐字错误（节点不存在 / 无资源 / 条目为 0）；
- **★ 水印两个维度**：**只有 `watermarkPref===1` 且 `isVip` 才直取原 URL**；
  否则 `watermark: pref!==1` ＋ **`communityWatermark: !isVip`**，**接口空则回落原 URL**
  ⟹ **"下载成功" ≠ "水印如你所愿"，交付前必须看画面**；
- **分组必打 ZIP**；单节点多产物仍是单文件；`zipSync level 6`；
- 视频强制 `mp4`；脚本导出 **CSV（UTF-8 BOM）**，动态角色列插在 `plotDescription` 之后，
  **`videoReference` 列取 `referenceFrameImage`**。

## 七、用户级水印偏好：**网页侧另有一条**（REA 静态 · 2026-10-16 补）

§六 讲的是**下载时**的水印参数（`watermarkPref` / `isVip`）；网页侧**还有一条用户级偏好**：

```text
POST ${config.apiHost}/api/canva/user/remove-watermark/get      ← 路径逐字是 canva（少一个 s）
headers: Accept / Content-Type: application/json / token
读 data.removeWatermark，仅接受 -1 | 0 | 1
存成 store 字段 exportWidthAIWaterMark（默认 -1）
失败（无 token / !ok / JSON 解析失败 / 值不在 {-1,0,1}）→ 整段 try/catch 静默，返回 null
```

**→ 判据**：**"导出宽度带不带 AI 水印"是服务端下发的三态偏好**；
**读失败会静默回落到默认 `-1`** ⟹ **拿不到值时，无法判断用户是"没开去水印"还是"请求挂了"**。
**⚠ 照抄 `/api/canva/…` 的拼写，不要"纠正"成 `canvas`。**
