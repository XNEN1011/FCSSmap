# FCSS 3D Hex Terrain Viewer

Flashpoint Campaigns: Southern Storm 地图数据的 3D 六边形地形可视化工具。

直接从游戏的 `.fp10` 二进制文件解析海拔与地形数据，无需 OCR 识别图片。

## 快速开始

### 1. 解析地图数据

```cmd
# 单张地图
python parse_fp10.py

# 全部 45 张地图
python parse_fp10.py --all
```

### 2. 打开 3D 视图

用浏览器打开 `hexmap.html`，拖入生成的 JSON 文件（如 `maps_json/Coburg.json`），即可交互浏览 3D 六边形地形。

## 文件说明

| 文件 | 用途 |
|------|------|
| `parse_fp10.py` | fp10 二进制解析器，提取每格 col/row/elevation/terrain |
| `hexmap.html` | Three.js 3D 渲染前端，支持旋转/缩放/悬停查看 |
| `maps_json/` | 45 张地图的解析结果（JSON） |
| `maps_index.json` | 地图索引（名称、尺寸、海拔范围） |
| `hex_data_fp10.json` | 默认单图输出 |

## fp10 格式

- 每个六边形一条变长记录
- 记录标记：`0x029A`（666，uint32 LE）
- 海拔 = 存储值 − 25（如存储 350 → 实际 325）
- Coburg 地图：81 × 40 = 3240 格，海拔 275–725

## 地图列表

| 地图 | 尺寸 | 海拔范围 |
|------|------|----------|
| Aichelberg | 46×30 | 325–825 |
| Amberg | 46×30 | 375–575 |
| Bamberg | 46×30 | 225–475 |
| Coburg | 81×40 | 275–725 |
| Colmar | 46×30 | 175–525 |
| Freiburg | 46×30 | 200–1025 |
| ... | ... | ... |

完整列表见 `maps_index.json`。

## 视图操作

| 操作 | 方式 |
|------|------|
| 旋转 | 鼠标左键拖拽 |
| 缩放 | 滚轮 |
| 平移 | 鼠标右键拖拽 |
| 查看详情 | 悬停六边形 |

## 技术栈

- Python + struct（fp10 解析）
- Three.js + OrbitControls（3D 渲染）
- InstancedMesh（大量六边形性能优化）

## 版本

- **v0.5.0** — fp10 二进制直接解析，支持 45 张地图批量提取，废弃 OCR 方案
