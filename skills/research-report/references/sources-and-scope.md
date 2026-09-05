# 来源、默认值与规范范围

## 写作与设计依据

这套风格最初的设计要求包括专业规范的书面版式、苹方、三线表、自然客观的中文和最终文件视觉检查。通用版本保留这些要求，主题、指标、章节与研究内容由实际项目决定。

公开参考如下：

- [IEEE Professional Communication Society：Write Effective Reports](https://procomm.ieee.org/communication-resources-for-engineers/written-reports/write-effective-reports/)：按读者需要组织报告，使用清晰层级、对齐与间距。
- [Proceedings of the IEEE：Guidelines for Figures and Tables](https://proceedingsoftheieee.ieee.org/resources/guidelines-for-figures-and-tables/)：选择有解释价值的图表，保持标记、字体、配色与清晰度一致。
- [Overleaf：How to generate and insert LaTeX tables](https://www.overleaf.com/learn/how-to/How_to_insert_tables_in_Overleaf)：参考 `booktabs` 的顶线、表头线与底线结构。
- [humanizer-zh](https://github.com/op7418/Humanizer-zh) 与 [oil-tone](https://github.com/oil-oil/oil-tone)：正式中文的事实边界、完整语法与平实表达。技能内的写作规则独立表述，不包含其个人身份设置，也不要求安装它们。

上述资料用于写作和设计参考。A4 单栏、各级字号、行距、页边距及蓝灰色值是本模板的默认选择。学位论文、期刊、机构或活动的强制格式仍以相应要求为准。

外部文档和字体不随技能分发，其权利与许可由各自权利人保留。

## Skill 文件格式

核对日期：2026-09-05。

- [Agent Skills Specification](https://agentskills.io/specification)：入口文件、YAML 元数据、命名、相对引用与渐进加载。
- [OpenAI：Build skills](https://learn.chatgpt.com/docs/build-skills)：技能发现、可选 `agents/openai.yaml` 和使用入口。
- [Agent Skills 官方参考验证器](https://github.com/agentskills/agentskills/tree/69ef37e9424c0a7ea9dd2293b559e43ec8176379/skills-ref)：固定提交 `69ef37e9424c0a7ea9dd2293b559e43ec8176379`，用于复核格式。

入口只保留任务选择和主要约束，详细规范按需读取。`agents/openai.yaml` 是可选的产品元数据；其余目录采用开放格式，不依赖特定模型、账号或服务接口。

格式验证检查文件结构与元数据；脚本测试检查可观察的工具行为。报告是否准确、清楚、适合读者，还需要对照真实材料和最终页面验收。使用其他客户端时按其安装方式放置技能目录。
