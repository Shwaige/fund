# 资产管家 (Fund Manager)

基于 Streamlit 的个人基金净值与盈亏实时监控系统。

### 🚀 核心逻辑
- **双路校验**：优先使用历史净值接口（T日与T-1日对照），数据未出时回退至实时估值接口。
- **数据一致性**：强制采用同源数据计算，确保盈亏精度。

# 1. 解锁脚本执行权限（如果报错需执行，不报错可跳过）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 2. 激活虚拟环境 (注意前面的点)
.\.venv\Scripts\Activate.ps1
source .venv/bin/activate

# 3. 启动资产管家程序
streamlit run fund_app.py

格式如下：
国泰黄金ETF联接C,004253,3486.39
天弘中证电网设备主题指数C,025833,872.29
国泰国证有色金属行业指数C,015596,456.78
华夏沪深300ETF联接A,000051,288.15
中航军民融合精选混合A,004926,303.92
安联中国精选混合A,021981,258.63
信澳转型创新股票C,015608,237.53