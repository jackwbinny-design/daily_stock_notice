import time
import logging
import os
from datetime import datetime, timezone, timedelta

# ==================== 业务核心配置区 ====================
# 从 GitHub Secrets 读取变量
FIXED_FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
FIXED_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

# 定时任务触发点（北京时间）：12:05 (午盘) / 17:05 (收盘)
SCHEDULE_TIMES = ["12:05", "17:05"]

# 精简后的核心ETF列表 (共12只，涵盖A股核心、跨境及行业)
STOCK_CODES = [
    "159326", # 沪深300ETF
    "512980", # 传媒ETF
    "588710", # 科创板
    "515880", # 轨道交通ETF
    "159851", # 金融科技ETF
    "588000", # 科创50ETF
    "159530", # 纳指ETF
    "513130", # 恒生科技ETF
    "589720", # 芯片ETF
    "560660", # 证券ETF
    "159206", # 创业板指
    "510330", # 沪深300龙头
]
# ========================================================

from src.feishu_doc import FeishuDocManager
from src.config import get_config
from src.core.pipeline import StockAnalysisPipeline
from src.core.market_review import run_market_review

def get_beijing_time():
    return datetime.now(timezone(timedelta(hours=8)))

def run_task():
    config = get_config()
    config.gemini_api_key = FIXED_GEMINI_KEY
    config.feishu_webhook = FIXED_FEISHU_WEBHOOK
    
    # 单线程运行
    pipeline = StockAnalysisPipeline(config=config, max_workers=1)
    now = get_beijing_time()
    logging.info(f"🚀 云端ETF专项分析启动 | 北京时间: {now.strftime('%H:%M:%S')}")
    
    results = []
    for i, code in enumerate(STOCK_CODES):
        logging.info(f"[{i+1}/{len(STOCK_CODES)}] 正在处理: {code}")
        try:
            res = pipeline.run(stock_codes=[code], dry_run=False, send_notification=False)
            if res: 
                results.extend(res)
            
        # 强制休眠 15 秒（RPM=5 的生死线是 12秒，15秒最稳）
        if i < len(STOCK_CODES) - 1:
            time.sleep(15)
        except Exception as e:
            if "429" in str(e):
                logging.warning("触发限流，额外休眠30秒...")
                time.sleep(30)
            else:
                logging.error(f"处理 {code} 异常: {e}")
            
    # 生成全市场复盘
    market_report = run_market_review(pipeline.notifier, pipeline.analyzer, pipeline.search_service)
    
    # 飞书云文档封装
    feishu_doc = FeishuDocManager()
    doc_title = f"{now.strftime('%m-%d %H:%M')} ETF决策仪表盘(云端版)"
    full_content = (f"# 📈 市场复盘\n\n{market_report}\n\n---\n\n" if market_report else "") + \
                   (f"# 🚀 ETF核心池仪表盘\n\n{pipeline.notifier.generate_dashboard_report(results)}" if results else "")
    
    doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
    if doc_url:
        pipeline.notifier.send(f"✅ 今日ETF内参已生成(共{len(results)}只)：\n{doc_url}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
    # GitHub Actions 环境判断
    if os.getenv("GITHUB_ACTIONS") == "true":
        run_task()
    else:
        run_task()
        while True:
            current_hm = get_beijing_time().strftime("%H:%M")
            if current_hm in SCHEDULE_TIMES:
                run_task()
                time.sleep(70)
            time.sleep(30)
