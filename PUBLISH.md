# 发布到 GitHub 完整步骤（Windows）

从零到「仓库能公开访问」，大约 10 分钟。命令都在 **PowerShell** 里执行。

---

## 0. 前置准备

### 0.1 有 GitHub 账号

没有就去 <https://github.com/signup> 注册（邮箱验证即可）。

### 0.2 安装 Git

检查是否已装：

```powershell
git --version
```

看到 `git version 2.x` 就跳过。没有的话：

```powershell
winget install --id Git.Git -e --source winget
```

装完**关掉并重开** PowerShell（让 PATH 生效），再 `git --version` 确认。

### 0.3 设置提交身份（只需一次）

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的邮箱@example.com"
```

邮箱建议和 GitHub 账号一致（不然提交记录不会算到你头上）。

### 0.4 检查本地目录是干净的

进入项目目录，确认只有该传的文件：

```powershell
cd C:\Users\LX\Doubao\chats\2026-10-13\new-chat\zhixue-reading-bot
dir
```

应该看到：`auto_read.py`、`check_env.py`、`requirements.txt`、`README.md`、`PUBLISH.md`、`LICENSE`、`.gitignore`。

> **不要**把智学网 APK、`VBCABLE.zip`、运行截图、账号密码一起传上去。体积大、还涉及隐私和版权。本项目的 `.gitignore` 已经挡住这些。

---

## 1. 在 GitHub 上创建空仓库

1. 打开 <https://github.com>，右上角 **+** → **New repository**；
2. **Repository name** 填 `zhixue-reading-bot`；
3. **Description** 可填：`智学网「文章朗读」作业自动完成脚本（安卓模拟器 + 虚拟声卡）`；
4. 选 **Public**（公开）或 **Private**（私有，只有自己可见）；
5. **不要勾选** "Add a README file"、".gitignore"、"License" —— 本地已经有，勾了会产生冲突，需要额外处理；
6. 点 **Create repository**。

创建完成后页面会显示仓库地址，形如：

```
https://github.com/<你的用户名>/zhixue-reading-bot.git
```

复制它，下一步要用。

---

## 2. 本地初始化并提交

在项目目录里依次执行：

```powershell
git init
git add .
git status          # 确认待提交清单里没有 apk / 截图 / 大文件
git commit -m "feat: 智学网文章朗读自动化脚本（模拟器+虚拟声卡）"
```

`git status` 里如果冒出 `*.apk`、`shots/`、`tmp_seg.mp3`，说明 `.gitignore` 没生效，先检查文件是否在根目录、名字是否为 `.gitignore`。

> 若提示 `warning: LF will be replaced by CRLF`，可以忽略；想消除就执行 `git config --global core.autocrlf true`。

---

## 3. 关联远程仓库并推送

```powershell
git branch -M main
git remote add origin https://github.com/<你的用户名>/zhixue-reading-bot.git
git push -u origin main
```

### 第一次推送会要求登录

GitHub 早已不支持「账号 + 密码」推送，必须用下面两种方式之一：

#### 方式 A：浏览器授权（推荐，最省事）

如果弹出 GitHub 登录窗口，按提示在浏览器里点 **Authorize** 即可。没弹窗就先执行：

```powershell
git config --global credential.helper manager
git push -u origin main
```

#### 方式 B：Personal Access Token（弹窗登录失败时用）

1. 打开 <https://github.com/settings/tokens> → **Generate new token (classic)**；
2. Note 随便填，Expiration 选 30 天或 90 天；
3. 勾选 **repo**（私有仓库必须，公开仓库也建议勾）；
4. 点 **Generate token**，复制那串 `ghp_xxxx...`（**只显示一次**）；
5. 再次 `git push -u origin main`，用户名填 GitHub 用户名，**密码处粘贴这个 token**（不是账号密码）。

token 建议存到密码管理器，别写进代码或 README。

---

## 4. 验证成功

刷新仓库页面，应该能看到：

- 文件列表里有 `auto_read.py`、`README.md` 等；
- 页面下方自动渲染出 README 内容（标题、原理图、表格都在）；
- 有 1 次 commit 记录。

顺手做三件小事：

1. 仓库页右上角 **⚙ Settings** → 填 Description、加 Topics（如 `python`、`uiautomator2`、`automation`）；
2. **About** 区域勾选/取消，让简介更清楚；
3. 若想加许可证入口，GitHub 会读 `LICENSE` 自动识别为 MIT。

---

## 5. 以后怎么更新

改完代码后：

```powershell
git status                     # 看改了什么
git add .
git commit -m "fix: 修复XX问题"
git push
```

想发版本（让别人下载 zip）：

```powershell
git tag -a v1.0.0 -m "首个可用版本"
git push origin v1.0.0
```

然后到仓库 **Releases** → **Draft a new release** → 选 `v1.0.0` → 发布。

---

## 6. 常见报错对照

| 报错 | 原因 | 解决 |
| --- | --- | --- |
| `remote: Support for password authentication was removed` | 用了账号密码 | 改用 token 或浏览器授权（见第 3 步） |
| `Permission denied (publickey)` | 走了 SSH 但没配密钥 | 把地址换成 `https://...`，或配置 SSH key |
| `Failed to connect ... port 443: Timed out` | 网络访问 GitHub 不通 | 开代理后执行 `git config --global http.proxy http://127.0.0.1:7890`（端口按你的代理改）；取消用 `git config --global --unset http.proxy` |
| `failed to push some refs` / `Updates were rejected` | 远程有你本地没有的提交（多半建仓库时勾了 README） | `git pull --rebase origin main` 再 `git push` |
| `src refspec main does not match any` | 还没提交，或分支名不是 main | 先 `git add . && git commit`，再 `git branch -M main` |
| `file is 123.00 MB; this exceeds GitHub's file size limit` | 传了大文件（APK 等） | `git rm --cached <文件>`，确认 `.gitignore` 已包含它，再重新提交 |
| `LF will be replaced by CRLF` | 换行符转换提示 | 无害；或 `git config --global core.autocrlf true` |

---

## 7. 发布前的自查清单

- [ ] `README.md` 里的截图/路径/端口说明与实际一致
- [ ] 没有提交任何 APK、安装包、账号、Cookie、个人作业截图
- [ ] `pip install -r requirements.txt` 在干净环境能装成功
- [ ] `python check_env.py` 能正常输出自检结果
- [ ] `LICENSE` 与 README 里的 License 声明一致
- [ ] 仓库可见性（Public / Private）符合你的预期

---

## 8. 可选：用命令行工具建仓库

装了 [GitHub CLI](https://cli.github.com/) 的话，可以跳过第 1 步的网页操作：

```powershell
winget install --id GitHub.cli -e --source winget
gh auth login          # 按提示在浏览器授权
gh repo create zhixue-reading-bot --public --source . --remote origin --push
```

一条命令完成「建仓库 + 关联 + 推送」。
