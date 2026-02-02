import time
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

# ==================== 核心配置区 ====================
FIXED_FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")
FIXED_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

# 定时任务(北京时间)
SCHEDULE_TIMES = ["12:05", "17:05"]

# 7只精选核心ETF（低压测试版）
STOCK_CODES = ["510330", "513130", "159326", "512980", "588000", "159530", "589720"]
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
    
    # 强制单线程
    pipeline = StockAnalysisPipeline(config=config, max_workers=1)
    now = get_beijing_time()
    logging.info(f"🚀 云端精选分析启动 | 北京时间: {now.strftime('%H:%M:%S')}")
    
    results = []
    for i, code in enumerate(STOCK_CODES):
        logging.info(f"[{i+1}/{len(STOCK_CODES)}] 正在处理: {code}")
        try:
            res = pipeline.run(stock_codes=[code], dry_run=False, send_notification=False)
            if res:
                results.extend(res)
            
            # --- 核心降压：休眠 15 秒确保 RPM <= 4 ---
            if i < len(STOCK_CODES) - 1:
                time.sleep(15)
        except Exception as e:
            logging.error(f"处理 {code} 异常: {e}")
            
    # 大盘复盘逻辑
    market_report = ""
    try:
        market_report = run_market_review(pipeline.notifier, pipeline.analyzer, pipeline.search_service)
    except:
        logging.error("大盘复盘失败，跳过")

    # 飞书生成
    try:
        feishu_doc = FeishuDocManager()
        doc_title = f"{now.strftime('%m-%d %H:%M')} ETF精选内参"
        full_content = (f"# 📈 市场复盘\n\n{market_report}\n\n---\n\n" if market_report else "") + \
                       (f"# 🚀 个股仪表盘\n\n{pipeline.notifier.generate_dashboard_report(results)}" if results else "")
        
        doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
        if doc_url:
            pipeline.notifier.send(f"✅ 精选ETF报告(共{len(results)}只)已生成：\n{doc_url}")
    except Exception as e:
        logging.error(f"飞书推送异常: {e}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
    # 适配 GitHub Actions 环境
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
