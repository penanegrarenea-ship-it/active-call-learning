# active-call-learning
非官方 active-call 中文学习课程；仅静态教学，不提供通话服务

## 课程性质

这是给简体中文读者的非官方静态课程，用来阅读 [active-call](https://github.com/miuda-ai/active-call) 已经公开的概念。它不是官方文档，也不代替上游仓库。

## 来源

课文锚定上游的一个固定提交，不跟随默认分支浮动：

- 仓库：[`miuda-ai/active-call`](https://github.com/miuda-ai/active-call)
- 版本：crate `0.3.120`
- 提交：[`d453c4f8d4525c9c44fc7c6a8076b9bb98ede123`](https://github.com/miuda-ai/active-call/commit/d453c4f8d4525c9c44fc7c6a8076b9bb98ede123)（2026-11-20 14:53 Asia/Tokyo）

课号、状态和路径写在 [`course-manifest.json`](course-manifest.json)。`learning_repo.lessons_commit` 仍是引入前三课的 `1eee016a7e82b6151dc3ce54df48337195e34b23`。没改过的课文和样式继续对这个提交。后来的增量按顺序留在 `content_commits` 里，新的一次不覆盖旧记录。`pages_sha256` 是这些公开文件的内容摘要，用来核对字节，不是提交哈希。

## 怎么阅读

用浏览器打开 [`index.html`](index.html)。

- **已可读：** 第 1 课「定位」、第 2 课「三种入口」、第 3 课「Playbook 与 Webhook」、第 4 课「配置端口安全」、第 5 课「Hello Playbook」、第 6 课「YAML 场景」、第 7 课「变量」，以及这七课的速查。
- **仅计划：** 后面六课只有题目。仓库里没有对应文件，首页也不链接它们。

页面使用相对路径，并共用 `assets/style.css`。把仓库下载到本地后，不启动服务器也可以直接打开这些 HTML。GitHub 网站上的文件页显示的是源码，不是排好的页面。

## 运行未验证

本仓库只提供静态阅读。这里没有安装或运行 active-call，没有电话、录音、付费接口，也没有下载模型。课文中的流程是示意，不能当成已经验证过的运行结果。

## 静态发布

[`.github/workflows/pages.yml`](.github/workflows/pages.yml) 在推送到 `main` 时，只把白名单文件交给 GitHub Pages：`index.html`、已发布的七课、已发布的七份速查，以及 `assets/style.css`。组装逻辑在 [`scripts/assemble_pages.py`](scripts/assemble_pages.py)，不会把整个仓库上传上去，也不安装构建依赖。

工作流文件本身不会开通 Pages。需要有仓库管理权限的人在 Settings → Pages → Build and deployment 里把 Source 选为 GitHub Actions。在此之前没有站点，本仓库也不宣称已经部署成功。
