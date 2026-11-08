# 网页客户端：鉴权过期判定、静默错误与请求装饰（【REA静态】）

**这一册只说三件事：客户端怎么判「登录过期」、哪些错误被静默、请求上被自动加了什么。**
出处：`outputs/libtv_rea_20261014/53_API客户端鉴权与错误策略.md`。
> ⚠ 与 `libtv-web-api-shapes.md` 的分工：那册讲**端点与请求体的形状**，**本册讲请求层的"失败怎么读"**。

## 一、★★ 登录过期不是一个码说了算

```text
code === -1 且 msg 含 "401"                      → 判为未授权
code === 10001：
   extra_msg 命中"无权限"正则
   （no permission / permission denied / not allowed / 无权限 / 没有权限 / 无操作权限 / 权限不足）
        → 【不是】登录过期（是"无权限"）
   否则                                            → 判为未授权
```

**★ `10001` 被"登录过期"和"无权限"复用**：看到 10001 **先看 `extra_msg`**，别直接判过期。

## 二、一次性锁与哨兵错误

- `notify401()` **只在首次通知监听者**，此后要 `resetUnauthorizedLock()` 才会再通知
  ⟹ **一次会话内登录过期只提示一次**；
- 抛给上层的是**自制错误**：`name = "AuthExpiredHandledError"` · `code = 10001` ·
  **`__authExpiredHandled = true`**（文案取 i18n `common:authGuardLogin`）。

**看到 `AuthExpiredHandledError` / `__authExpiredHandled` ＝「已经处理过的登录过期」**，别再当普通失败重试。

## 三、★★ 哪些失败**不会**进错误上报

| 条件 | 处理 |
|---|---|
| `code` ∈ **{10050, 10051, 10101}** | **任何方法**都静默 |
| `GET` ＋ `/api/canvas/project/share/detail` 或 `/api/canvas/project/detail` ＋ `code === 30001` | 静默 |
| `GET` ＋ `/api/task/generation/detail` ＋ `code === 10000` | 静默 |

**判据**：这几处**非 0 是预期内**，别当故障报；**但"没上报"≠"成功"**。

## 四、每个请求都带的四个头

`webid` · `x-language`（取 cookie，缺省 **`zh`**）· **`X-Log-ID`**（每请求一个）· `token`（取 cookie，仅存在时）。
**调用方给的头会盖在上面**。

## 五、错误上报长什么样

事件名 **`libtv.api.request.error`**；前缀 **`[METHOD] url`**；
带 `code` / `requestParams` / `requestBody` / `requestHeaders` / `response` / `error`（＋ `causeMessage` / `causeStack`）。
**★ 客户端已把 `token` / `authorization`（键名**大小写不敏感**）脱敏成 `***`。**

## 六、被客户端**自动加上**的字段

- `bizScene` 注入**请求体**（枚举逐字：**`DEFAULT = 0`** · **`ACADEMY_PRACTICE = 10`**）；
- `courseUuid` 注入**查询参数**。

**判据**：抓到的请求里出现这两个字段，**可能是客户端加的，不是你写的**。

## 七、边界

1. 全部为只读静态证据；**未发请求、未触发任何鉴权分支**；
2. `code` 分类是**客户端怎么读**，**不是服务端契约**；
3. 静默白名单**只读到这 5 个码 / 3 条路径**，**可能不全**；
4. 这些文件尾部**有 `sourceMappingURL`，但本轮 `.map` 一张都没采到**
   ⟹ **下次抓包把 `.map` 一并拉下来**，能把"读压缩产物"升级成"读源码"。
