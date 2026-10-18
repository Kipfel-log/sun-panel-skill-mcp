# OpenAPI v1 合约摘要

官方资料：
- https://doc.sun-panel.top/openapi/v1/
- https://doc.sun-panel.top/openapi/v1/apis_item_group.html
- https://doc.sun-panel.top/openapi/v1/apis_item.html
- https://doc.sun-panel.top/openapi/v1/other.html

核对日期：2026-10-18。全为 POST，JSON 请求体，`token` 请求头。业务 `code=0` 才算成功。`1202` 为唯一标识冲突，`1203` 为记录不存在；官方通用错误码表的 token/参数说明存在不一致，保留实际 code，不凭单个错误码推断需要更换令牌。

| 操作 | 路径（相对 /openapi/v1） | 请求字段 |
|---|---|---|
| 版本 | version | 空对象 |
| 所有分组 | itemGroup/getList | 空对象 |
| 单个分组 | itemGroup/getInfo | itemGroupID 或 onlyName |
| 单个入口 | item/getInfoByOnlyName | onlyName |
| 新增入口 | item/create | url；其他字段可选 |
| 修改入口 | item/update | onlyName；其他字段可选 |

入口可选字段：`title`、`iconUrl`、`url`、`lanUrl`、`description`、`itemGroupID`、`itemGroupOnlyName`、`isSaveIcon`。本封装为便于查重和验证，新建也要求 `onlyName`。

例：`{"onlyName":"nav-example","title":"示例应用","url":"https://example.com","itemGroupID":2}`。所有示例域名都是占位符。

分组响应在 `data.list`，含 `itemGroupID/title/onlyName`；部分现有分组 onlyName 为空，此时用数字 ID。没有公开的入口 getList、删除、分组写入或外观配置接口。批量修改仅支持 v2.0.0-dev-13+，未在此封装暴露。

实际观察到：1.8.1 的 `getInfoByOnlyName` 可能返回空 `iconUrl`，但页面仍使用已保存的图标。因此空读回值不能证明图标写入失败，也不能用它覆盖现有图标。图标写入返回 `needs_visual_check` 时，检查页面实际图片加载结果，不重试已接受的写入。

1.8.1 修复了部分字段更新影响原图标的问题。封装将修改操作限制为稳定版 1.8.1+，并只发送显式修改字段：[上游版本说明](https://github.com/hslr-s/sun-panel/releases/tag/v1.8.1)。
