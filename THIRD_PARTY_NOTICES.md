# 第三方代码与参考资料

## 已整合：UAV-Downloader

- 项目：https://github.com/Alos21750/UAV-Downloader
- 作者：ALOS / Alos21750 及该项目贡献者。
- 固定提交：`3cb9f07af934373a90ef1de822b5696efb98623c`。
- 原文件：`src/uav_downloader/sites/huangguo.py`。
- 原代码许可证：Apache License 2.0，完整文本见 `licenses/UAV-Downloader-Apache-2.0.txt`。
- 派生代码：`hg_downloader/vendor/uav_huangguo.py`。

复用了 `_retry_after` 的服务端等待时间解析，以及 `_initial_data`、
`_fetch_episodes_uncached` 的公开页面元数据和分集链接解析逻辑。
修改包括：用标准库 `HTMLParser` 替换 BeautifulSoup、适配用户提供的镜像域名、
转换为本项目的剧集结构、移除上游爬虫框架依赖。

这些代码实际用于 API 元数据不可用时的 HTML 备用解析，以及网络重试的
`Retry-After` 处理。本项目没有整合其多站点界面、监控、字幕模型或其他站点适配。
上游源文件没有额外的版权行；其原有模块说明和本项目修改范围已在派生文件中注明。

## 参考但未复制代码

- yt-dlp：https://github.com/yt-dlp/yt-dlp ，查阅 `yt_dlp/downloader/external.py` 中
  `FFmpegFD` 的请求头、流复制和临时输出处理方式。
- N_m3u8DL-RE：https://github.com/nilaoda/N_m3u8DL-RE ，参考其 HLS 下载工具说明。

本项目的下载器通过外部 FFmpeg / FFprobe 可执行文件工作，没有捆绑二进制。
FFmpeg 的具体许可证取决于所使用的构建配置。
