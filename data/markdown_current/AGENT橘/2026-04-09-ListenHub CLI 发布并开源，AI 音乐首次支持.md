---
title: "ListenHub CLI 发布并开源，AI 音乐首次支持"
author: "AGENT橘"
date: "2026-04-09 13:36"
source: "https://mp.weixin.qq.com/s/SRDnce3f44RTLv3ZepbIOw"
---

> ListenHub CLI 发布并开源了。npm install -g 装完就能用，各种 Agent 里直接跑。


ListenHubCLI发布并开源了。npminstall-g装完就能用，各种Agent里直接跑。

这次除了之前就有的播客、TTS、解说视频，新加了两个能力：

AI音乐生成和PPT幻灯片。

先说音乐。

给一段文字描述，直接出一首曲子：

想要纯音乐、没人声的，加个--instrumental：

还有个cover翻唱功能，丢一段本地音频进去就行。支持mp3、wav、flac、m4a、ogg、aac，最大20MB。CLI会自动上传到云端再调接口，不用你操心：

URL也行，直接透传：

给个主题就能生成一套幻灯片，带配音的那种：

SDK里能看到更多细节，可以指定模板类型、语言、尺寸、页数这些：

播客、TTS、解说视频这些老能力都在。

播客支持quick、deep、debate三种模式，可以丢参考链接进去：

TTS一行命令搞定：

图片生成支持传本地参考图，最多可以传多张：

所有创作命令都支持--json输出和--no-wait异步模式，方便写脚本串联：

底层SDK也一起开源了，TypeScript写的，包名@marswave/listenhub-sdk。

OAuth登录、自动刷token、429重试这些都处理好了。装上就能在自己的项目里集成：

用起来很直白：

SDK的repo里有完整的示例代码，播客、TTS、解说视频、幻灯片、音乐、图片每个都有。

Node.js>=20，然后：

装完先登录：

会弹浏览器授权，token存在~/.config/listenhub/credentials.json，过期自动刷新。

更新的话重新装一遍就行：

CLI:https://github.com/marswaveai/listenhub-cli

SDK:https://github.com/marswaveai/listenhub-sdk

都是MIT协议，随便用。
