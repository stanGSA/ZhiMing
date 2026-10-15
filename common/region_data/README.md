# 出生地点行政区快照

`regions.json.gz` 是只读的 GeoNames 派生数据，按 **CC BY 4.0** 使用与再分发。

- 来源：[GeoNames](https://www.geonames.org/)、[GeoNames 数据下载](https://download.geonames.org/export/dump/)、`geonamescache` 3.0.2 中的 `cities15000.json` 和 `countries.json`。
- 许可：[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)。GeoNames 是原始数据提供方；本项目仅筛选、整理层级、选取中文别名并压缩，不代表提供方认可本应用。
- 快照日期：2026-10-15。数据共 38,262 个层级节点，其中中国大陆包含 31 个省级、360 个地级、2,938 个县级行政区域；另包含全球城市及其省州层级。香港、澳门、台湾沿用来源的单独地区入口。
- 全球其他地区基于 cities15000 城市数据，**未提供全球区县完整覆盖**。页面明确标注没有区县层级的城市，不把市中心伪装成县区地址。
- 经纬度是 WGS84 的行政区中心或城市中心，不是具体医院坐标。8 个中国县区原记录缺少时区时，沿用 GeoNames 所属省份的时区，并在 `timezone_source` 中标记；新疆仍须用户选择出生钟表时间制。
- GeoNames 行政区和别名可能存在更新滞后。不存在的区县不会替换成相邻城市；需要更新时应重新生成快照并验证数据。

再生成命令：`python -m scripts.build_regions`。输入文件放在被 Git 忽略的 `data/geo/`：

1. `CN.snapshot.zip`：GeoNames `CN.zip` 的完整快照。
2. `admin1CodesASCII.txt`：GeoNames 一级行政区名称表。
3. `geonamescache-3.0.2.whl`：项目数据清单中已有的固定版本。

生成器只读取数据，不执行下载的代码。每个输入文件的 SHA256 保存在压缩文件内的 `metadata.inputs` 中。此小型派生快照随项目分发，因此普通用户无需下载完整的中国地名库。
