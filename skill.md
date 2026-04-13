---
name: pr_download
description: 当用户需要以下操作时使用此 skill：
1. 下载指定 GitHub PR 的代码变更
2. 在本地审查 PR 代码
3. 本地测试 PR 的功能
4. 准备合并前的代码检查
---

下载并处理 GitHub Pull Request 的 skill。支持将 PR 的代码变更下载到本地工作目录，便于代码审查和本地测试。



## 前置条件

- 已安装 `gh` (GitHub CLI) 工具
- 已配置 GitHub 认证 (`gh auth login`)
- 当前目录是一个 git 仓库或可以克隆目标仓库

## 工作流程

### 步骤 1: 解析 PR 信息

从用户输入中提取：
- 仓库地址 (owner/repo)
- PR 编号

### 步骤 2: 获取 PR 详情

使用 `gh pr view` 命令获取 PR 信息：
- 标题和描述
- 作者信息
- 基础分支和目标分支
- 文件变更列表

### 步骤 3: 下载 PR 代码

根据场景选择下载方式：

**方式 A - 检出 PR 分支**:
```bash
gh pr checkout <PR_NUMBER>
```

**方式 B - 下载为补丁文件**:
```bash
gh pr diff <PR_NUMBER> > pr_<PR_NUMBER>.patch
```

### 步骤 4: 验证下载

- 确认文件已正确下载
- 显示变更统计信息
- 列出修改的文件

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pr_url` | string | 是 | PR 的完整 URL 或简短标识 (owner/repo/number) |
| `output_dir` | string | 否 | 输出目录，默认为当前目录 |
| `format` | string | 否 | 下载格式: `checkout` 或 `patch`，默认为 `checkout` |

## 示例

### 示例 1: 通过 URL 下载 PR

**用户输入**:
```
下载这个 PR: https://github.com/owner/repo/pull/123
```

**执行步骤**:
1. 解析 URL 提取 owner/repo 和 PR 编号 123
2. 运行 `gh pr checkout 123`
3. 显示变更文件列表

### 示例 2: 下载为补丁文件

**用户输入**:
```
下载 PR #456 为补丁文件
```

**执行步骤**:
1. 运行 `gh pr diff 456 > pr_456.patch`
2. 确认补丁文件已创建
3. 显示补丁统计信息

## 输出格式

成功执行后返回：

```
✅ PR #<NUMBER> 下载成功

📋 PR 信息:
   标题: <PR_TITLE>
   作者: <AUTHOR>
   分支: <HEAD_BRANCH> → <BASE_BRANCH>

📁 变更文件:
   - <FILE_PATH_1>
   - <FILE_PATH_2>
   ...

📊 统计:
   新增: +<ADDITIONS> 行
   删除: -<DELETIONS> 行
   文件: <CHANGED_FILES> 个
```

## 错误处理

| 错误类型 | 处理方式 |
|---------|---------|
| PR 不存在 | 提示用户检查 PR 编号是否正确 |
| 认证失败 | 引导用户运行 `gh auth login` |
| 网络错误 | 重试或提示检查网络连接 |
| 权限不足 | 提示用户检查仓库访问权限 |

## 注意事项

1. 下载前会检查本地是否有未提交的变更，避免覆盖
2. 支持 GitHub Enterprise，需配置相应的主机地址
3. 大型 PR 可能需要较长时间下载，建议显示进度

## 相关命令

```bash
# 查看 PR 信息
gh pr view <NUMBER>

# 检出 PR
gh pr checkout <NUMBER>

# 查看 PR diff
gh pr diff <NUMBER>

# 列出 PR 文件
gh pr diff <NUMBER> --name-only
```

## 扩展功能

- [ ] 支持下载特定文件
- [ ] 支持下载 PR 的评论和审查记录
- [ ] 支持批量下载多个 PR
- [ ] 支持下载 PR 的 CI/CD 日志
