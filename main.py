import time
import logging
import os
from datetime import datetime, timezone, timedelta

# ==================== 业务核心配置区 ====================
# GitHub 环境下，我们将从 Secrets 读取这两个变量
FIXED_FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "你的飞书链接保底")
FIXED_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "你的Key保底")

# 定时任务触发点（北京时间）：12:05 (午盘) / 17:05 (收盘)
SCHEDULE_TIMES = ["12:05", "17:05"]

# 74只全量股票池
STOCK_CODES = [
    "159326", "512980", "588710", "515880", "159851", "588000", "159530", "513130", "589720", "560660", "159206", "510330",
    "300058", "301171", "002400", "300442", "300738", "600673", "300308", "300394", "300502", "300757", "688041", "688256", 
    "002851", "300593", "300857", "002463", "300620", "688498", "300418", "300383", "002112", "002202", "300762", "002465", 
    "002050", "601689", "600031", "603728", "002472", "688017", "600580", "600309", "000301", "601899", "600141", "002258", 
    "600596", "000830", "603225", "002895", "300505", "600230", "600800", "002001", "002487", "300274", "003035", "002837", 
    "000831", "601336", "300803", "002916", "002436", "300536", "603200", "300450", "688772", "301520", "002371", "688012", 
    "301200", "001267"
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
    
    # 单线程 + 冷却，确保云端运行极其稳定
    pipeline = StockAnalysisPipeline(config=config, max_workers=1)
    now = get_beijing_time()
    logging.info(f"🚀 云端任务启动 | 北京时间: {now.strftime('%H:%M:%S')}")
    
    results = []
    for i, code in enumerate(STOCK_CODES):
        res = pipeline.run(stock_codes=[code], dry_run=False, send_notification=False)
        if res: results.extend(res)
        if i < len(STOCK_CODES) - 1: time.sleep(2) # 云端 IP 质量好，2秒即可
            
    market_report = run_market_review(pipeline.notifier, pipeline.analyzer, pipeline.search_service)
    
    feishu_doc = FeishuDocManager()
    doc_title = f"{now.strftime('%m-%d %H:%M')} 决策仪表盘(云端版)"
    full_content = (f"# 📈 市场复盘\n\n{market_report}\n\n---\n\n" if market_report else "") + \
                   (f"# 🚀 个股仪表盘\n\n{pipeline.notifier.generate_dashboard_report(results)}" if results else "")
    
    doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
    if doc_url:
        pipeline.notifier.send(f"✅ 云端内参已生成：\n{doc_url}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
    # GitHub Actions 环境直接运行一次后退出
    if os.getenv("GITHUB_ACTIONS") == "true":
        run_task()
    else:
        # 本地保留定时逻辑方便调试
        run_task()
        while True:
            current_hm = get_beijing_time().strftime("%H:%M")
            if current_hm in SCHEDULE_TIMES:
                run_task()
                time.sleep(70)
            time.sleep(30)
