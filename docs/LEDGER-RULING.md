# 混合模板月度发布裁决书

## 背景

考勤机分批升级，同一结算月的源文件同时存在：

- 旧字段模板：整分钟打卡，休息用 `break_start/break_end` 起止时刻；
- 新字段模板：打卡带秒，休息用整数 `break_minutes`；
- 工资截止前还会混入晚到文件。

全月只认一套模板会让旧文件整批隔离；逐行猜格式可能把同一班次拆成两种解释。

## 裁决

1. **文件级模板认定，禁止逐行猜测。** 表头签名决定整份文件的解释方式（v1/v2）。签名矛盾（新旧休息字段并存、都缺、缺共用必填列、表头重复）整份文件 `TEMPLATE` 拒收。认定结果随文件登记，页面逐来源可见。
2. **先归一、后配对，同班次不拆。** v2 的休息分钟按实际打卡区间中点居中合成休息窗口，与 v1 同构后复用同一条配对、切段、倍率、金额链路。IN/OUT 模板不一致或休息参数冲突按 CONFLICT 整班隔离。
3. **带秒可采信、按分钟计薪。** v1 维持整分钟强校验；v2 允许秒，工作分钟按秒折整分钟向下截断，原始带秒时刻全程保留。
4. **来源集指纹驱动版本。** 晚到文件随时登记；数据集指纹覆盖全部来源内容、参数与规则版本。重试同一来源幂等，记录不增不减。
5. **来源变动即作废、重新核对。** 同名文件内容变化后重算生成新数据集，旧发布版标记作废但不删除；发布指针原子切换，新版发布前旧版继续对外有效，发布中断不影响旧版；任何版本的原始打卡都可查。
6. **页面与导出同源。** 核对页与导出 CSV 都取自同一数据集，含每来源解释方式、原始打卡、班次配对与最终应付；仅已发布数据集允许导出。

## 落点

| 关注点 | 位置 |
|---|---|
| 表头签名裁决 | `app/modules/m8_ledger/profiles.py` |
| 逐文件读取与整份拒收 | `app/modules/m8_ledger/source_reader.py` |
| 归一化与跨文件去重 | `app/modules/m8_ledger/canonicalize.py` |
| v2 居中休息窗 | `app/modules/m8_ledger/break_window.py` |
| 模板感知配对 | `app/modules/m3_versions/rules.py` |
| 带秒切段 | `app/modules/m4_segments/rules.py` |
| 月度管线与来源汇总 | `app/modules/m8_ledger/pipeline.py` |
| 版本/作废/发布指针 | `app/modules/m8_ledger/ledger_store.py` |
| 页面与接口 | `app/modules/m8_ledger/handler.py`、`app/templates/m8_ledger.html` |
| 同源导出 | `app/modules/m8_ledger/export_monthly.py` |
| 混合样例 | `sample_data/month_2026_10/`（含 UTF-8 BOM、GB18030、晚到、拒收文件） |
| 验证 | `tests/test_ledger_month.py` |
