---
title: "我做Claude Code榜一大哥的时候，OpenClaw的作者Peter是榜三……当时他在干啥？"
author: "刘小排r"
date: "2026-02-27 00:46"
source: "https://mp.weixin.qq.com/s/ZkqqPH_Go0RLsbma3l1J5g"
---

> 当时Peter还没开始做OpenClaw，他用这么多Token在干啥？


哈喽，大家好，我是刘小排。

前几天有位关注我公众号的朋友给我留言，他发现了一件有趣的事——去年我做ClaudeCode榜一大哥的时候，OpenClaw的作者PeterSteinberger是榜三……😱

(什么“榜一大哥”？到这里补网速揭秘ClaudeCode榜一大哥：一个AI创业者如何把工具用到极致|对话刘小排）

仔细看了一下榜单（上图2），发现了：

如果按照‘Token折合多少美金’计算，我是第一，Peter是第三。

但是如果按照‘消耗了多少Token’计算，Peter比我用得更多，多10%（说明当时他更喜欢用sonnet模型，而我总是无脑用最贵的Opus）

那是2025年7月和8月的事了。当时，Peter还没开始做OpenClaw。那他当时在干什么呢？

我找到了Peter的Github主页。

他从2025年4月开始，几乎就是每天都提交代码的状态了。下图是Peter的Github日历。

我偶尔会打酱油，但是我提交得也不少。下图是我的Github日历。

我从Peter的博客找到了一些蛛丝马迹

https://steipete.me/

Peter当时在做这些事情：

先是8月5号的Poltergeist，他在造一个很具体的基础设施级工具：通过自动watch&rebuild，帮人类和AIagent把“编译这一步”从心智中拿掉，让开发-测试循环更快。这就是典型的「为自己的痛点做工具，然后顺便变成产品」的路子。

到了8月19号的JustOneMorePrompt，你能感觉到他意识到自己已经有点「Claudoholic」了：长期高强度用ClaudeCode写工具、造agent、跑循环，他开始反思AI成瘾、极限工作文化和“效率”与“自我消耗”之间的边界。也就是在问：一直再来一个prompt，代价是什么？

8月21号的EssentialReadingforAgenticEngineers，则是在把过去一段时间踩坑、观察整理成一套「agenticengineer要看的底层认知」：开发者角色怎么演化、初级工程师怎么被新范式冲击、生产力的真实增益到底在哪、平台和MCP会在哪些地方坑你。

8月25号的MyCurrentAIDevWorkflow，则很像一个阶段性总结：他折返到一个自己验证过、真正稳定高效的组合——终端用Ghostty，旁边挂VSCode，核心驱动力是ClaudeCode。前面那些工具（比如Poltergeist）和认知（agenticengineering的套路），都沉淀成他日常写代码、带agent干活的固定workflow。

所以那段时间，Peter在做的事情可以概括成一句话：

用AI作为主力生产力，亲手搭起一整套「agentic开发流水线」（工具+流程+心智模型），一边加速shipping，一边试图搞清楚这种新工作方式对人本身的影响。

我们再分析Peter的Github，2025年7月和8月他在干啥：

VibeMeter（7月最重）48次提交，集中在7月1日-7月4日主要是UI/性能优化、分析能力增强仓库：steipete/VibeMeter

个人网站/博客steipete.me37次提交，覆盖7月2日-8月27日持续发技术文章（AIworkflow、Poltergeist、CLI等）+站点维护仓库：steipete/steipete.me

Matcha33次提交，集中在7月29日-7月30日新建并快速迭代的SwiftTUI项目（含测试/CI修复）仓库：steipete/Matcha

bench27次提交，集中在8月29日-8月30日T3/Reactplayground+数据库驱动基准测试工具方向仓库：steipete/bench

poltergohst6次提交，集中在8月5日Poltergeist的Go版实验实现（含Watchman相关修复）仓库：steipete/poltergohst

stats-store（辅助项目）4次提交，7月2日-7月24日主要是VibeMeterappcast/下载端点相关仓库：steipete/stats-store

从上面两个素材来看，

Peter在2025年7–8月在一边做AI时代的开发工具实验，一边把经验沉淀成公开文章和工作流框架。

边做实验，边开发工具，边写方法论，再把方法论也变成工具。

直到积累了大量经验，Peter从2025年11月24日，才开始做OpenClaw。

也有欣慰的地方，发现我和Peter在使用ClaudeCode的时候，有非常多的共同点。

（如果你对我那段时间如何使用ClaudeCode感兴趣，可以查看这篇播客揭秘ClaudeCode榜一大哥：一个AI创业者如何把工具用到极致｜对话刘小排）

从来不考虑节省Token，而是致力于花更多的Token，节省自己的时间。

一直在想办法减少人类参与，让AIAgent尽可能长时间的、自动运行。

早早就打开了BypassPermission权限，尽可能给AIAgent更大的权限，而不是畏首畏尾，担心AI搞坏。

都在用AI作为“研究+执行”助手，而不只是用来写代码。

喜欢做实验。

沉淀经验、沉淀工作流。

Peter做的东西和赚钱、商业化都毫无关系，他只是沉浸在自己的好奇心里。

甚至于，去年年中他重度投入的几个项目，现在都已经关闭、不再维护了，如steipete/bench、/steipete/Matcha、/steipete/VibeMeter等等，其中不乏有好几百个stars的好项目。而我相对要功利一些。

从去年年中的情况来看，他更喜欢做实验，我更喜欢做(能商业化的)产品。

Peter非常喜欢让AIAgent做自动化测试、CI。从他提交的代码看，有相当大的比例，和自动化测试、CI相关。

Peter的工具产品化能力更强。他比较喜欢把自己的工作流(workflow)沉淀成工具，让别人使用。包括OpenClaw，也是这样的产物。

Peter的数据化运营意识比我强多了。

无论是让AI做了什么，他总是想办法把其中的一切带上数据监控。

Peter的内功非常强，包括对软件工程的理解、对操作系统的理解、对CI的理解等等。

这方面我可太惭愧了。

记得在今年2月初真格基金组织的OpenClaw早期用户见面会上，已经有人发现了我和Peter使用ClaudeCode的方式很像了，他问我：为啥你不做个OpenClaw呢？

我回答说，Peter对操作系统的理解、软件工程内功比我强太多了，我只是一个玩家，而Peter是大师。

把经验变成可复用工具。

Peter早期的VibeMeter、Poltergeist，现在的OpenClaw，都有这条方法论的影子。

工作流工程化。

目前我的工作流都在脑海里面，有一些会写成公众号文章，还有一些在课程里，但是，都没有做到“工程化”，而是让读者自己去悟。而且，考虑到读者往往没啥耐心，我写得也很简略，生怕曲高和寡、平台不给我流量了。

这部分我是可以去加强的。

把AI自动化测试和CI补起来。除了产品交互，一律不再做人工测试。

目前我更还挺享受让AI做一大堆，等我睡觉起来之后，人工验收的。感谢Peter的提醒，我发现完全可以改进，让自己打更多酱油、让AI牛马发挥更多的价值。

既然已经不为钱发愁了，我可以放手做一些好玩的、对世界有更大影响的事情。

OpenClaw我非常喜欢。但愿有朝一日我也能做出来这样的产品，不是为了能赚多少钱(OpenClaw零商业化），而是为了真正的让世界变得有所不同，哪怕一点点也可以。

你有从Peter身上学到什么吗？欢迎评论区交流
