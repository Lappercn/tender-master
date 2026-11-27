# 爬虫定时调度器使用说明

## 功能概述

这个定时调度器可以按顺序启动多个爬虫脚本，每个脚本之间间隔5分钟，避免资源冲突和网络压力。

## 支持的爬虫脚本

1. **CFCPN招标信息采集** (`cfcpn_spider.py`)
   - 采集CFCPN网站的招标信息
   - 运行参数: `run --headless`

2. **千里马登录采集** (`login_spider.py`)
   - 采集千里马网站的招标信息
   - 运行参数: `test` (立即运行模式)

3. **中国招标投标公共服务平台** (`cebpubservice_spider.py` / `wj_spiders/wj_cebpubservice_china.py`)
   - 采集中国招标投标公共服务平台（`bulletin.cebpubservice.com`）26 个全行业招投标信息
   - 运行参数: `--now` (立即运行模式，如 `python wj_spiders/wj_cebpubservice_china.py --now`)

4. **中国烟草行业招标采集** (`tobacco_spider.py`)
   - 采集中国烟草行业招标信息
   - 运行参数: `run --headless`

## 使用方法

### 方法一：使用批处理文件（推荐）

#### 启动定时调度器
```bash
# 双击运行或在命令行执行
start_scheduler.bat
```
- 默认每天15:50自动执行所有爬虫脚本
- 按 `Ctrl+C` 可以停止调度器

#### 立即执行爬虫任务
```bash
# 双击运行或在命令行执行
run_now.bat
```
- 立即执行所有爬虫脚本，无需等待定时

### 方法二：使用Python命令

#### 启动定时调度器
```bash
python scheduler.py
```

#### 立即执行爬虫任务
```bash
python scheduler.py --now
```

#### 查看当前状态
```bash
python scheduler.py --status
```

#### 停止所有正在运行的进程
```bash
python scheduler.py --stop
```

#### 自定义执行时间
```bash
python scheduler.py --time 15:50
```

## 执行顺序和时间安排

1. **CFCPN招标信息采集** - 立即开始
2. **等待5分钟**
3. **千里马登录采集** - 开始执行
4. **等待5分钟**
5. **中国招标投标公共服务平台** - 开始执行
6. **等待5分钟**
7. **中国烟草行业招标采集** - 开始执行

## 日志文件

所有日志都会保存在 `logs/` 目录下：
- `scheduler.log` - 调度器主日志
- `cfcpn_spider.log` - CFCPN爬虫日志
- `login_spider.log` - 千里马爬虫日志
- `main_spider.log` - 招标平台爬虫日志
- `tobacco_spider.log` - 烟草爬虫日志

## 注意事项

1. **确保所有爬虫脚本文件存在**：调度器会检查脚本文件是否存在
2. **网络连接**：确保网络连接正常，特别是访问目标网站
3. **MongoDB服务**：确保MongoDB服务正在运行
4. **Chrome浏览器**：确保系统已安装Chrome浏览器
5. **Python依赖**：确保已安装所需的Python包（selenium、pymongo等）

## 错误处理

- 如果某个脚本执行失败，调度器会继续执行下一个脚本
- 所有错误信息都会记录在日志文件中
- 可以通过 `--status` 参数查看当前运行状态

## 自定义配置

如需修改脚本配置，可以编辑 `scheduler.py` 文件中的 `script_configs` 列表：

```python
self.script_configs = [
    {
        'name': '脚本名称',
        'script': '脚本文件名.py',
        'args': ['参数1', '参数2'],
        'description': '脚本描述'
    },
    # ... 更多脚本配置
]
```

## 系统要求

- Python 3.7+
- Chrome浏览器
- MongoDB数据库
- Windows/Linux/macOS系统

## 故障排除

1. **脚本文件不存在**：检查脚本文件是否在正确位置
2. **权限问题**：确保有足够的权限运行脚本
3. **依赖包缺失**：运行 `pip install -r requirements.txt`
4. **Chrome驱动问题**：确保Chrome浏览器版本与驱动兼容
5. **MongoDB连接失败**：检查MongoDB服务是否运行

## 联系支持

如有问题，请查看日志文件或联系技术支持。
