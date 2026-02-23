import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

def get_earnings_tickers(api_key):
    """透過 FMP API 獲取近兩日發布財報的美股代號"""
    # 轉換為美東時間基準 (UTC-5)
    today = datetime.utcnow() - timedelta(hours=5) 
    start_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    url = f"https://financialmodelingprep.com/api/v3/earning_calendar?from={start_date}&to={end_date}&apikey={api_key}"
    
    try:
        print(f"📥 正在向 FMP 請求 {start_date} 至 {end_date} 的美股財報日曆...")
        res = requests.get(url, timeout=15)
        if res.status_code != 200:
            print(f"⚠️ FMP API 回應異常: {res.status_code}")
            return []
            
        df = pd.DataFrame(res.json())
        if df.empty:
            return []
            
        # 排除非美股 (排除含有 . 的代號如 TSX 等)
        df = df[~df['symbol'].str.contains(r'\.')]
        tickers = df['symbol'].unique().tolist()
        print(f"✅ 成功獲取 {len(tickers)} 檔發布財報的美股代號。")
        return tickers
    except Exception as e:
        print(f"❌ 獲取財報日曆失敗: {e}")
        return []

def filter_us_ep_candidates(tickers, max_cap=10000000000, max_vol=1500000):
    """執行 yfinance 核心濾網：YoY > 39%、市值 < 10B、均量 < 1.5M"""
    print(f"🔍 開始執行營收 YoY 與冷落濾網，預計耗時數分鐘...")
    ep_list = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 1. 營收成長過濾 (revenueGrowth > 0.39)
            rev_growth = info.get('revenueGrowth')
            if rev_growth is None or rev_growth < 0.39:
                continue
                
            # 2. 市值過濾 (< 10 Billion USD)
            market_cap = info.get('marketCap')
            if market_cap is None or market_cap > max_cap:
                continue
                
            # 3. 籌碼過濾 (< 1.5M Shares)
            vol = info.get('averageVolume')
            if vol is None or vol > max_vol:
                continue
                
            ep_list.append({
                'Ticker': ticker,
                'Name': info.get('shortName', ticker),
                'YoY(%)': round(rev_growth * 100, 1),
                'MarketCap(B)': round(market_cap / 1e9, 2),
                'AvgVol(K)': round(vol / 1000, 1)
            })
            
        except Exception:
            pass
        # 避免觸發 yfinance 阻擋，加入微小延遲
        time.sleep(0.2) 
        
    return pd.DataFrame(ep_list)

def send_to_discord(content):
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("⚠️ 未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return
        
    if len(content) > 1950:
        content = content[:1950] + "\n...(名單過長已截斷)"
    requests.post(webhook_url, json={"content": content})
    print("✅ 成功發送至 Discord！")

if __name__ == "__main__":
    fmp_key = os.environ.get('FMP_API_KEY')
    if not fmp_key:
        print("❌ 找不到 FMP_API_KEY，請確認 GitHub Secrets 設定。")
        exit()
        
    today_str = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d')
    print(f"🚀 啟動美股 NTRT 盤前掃描 ({today_str})")
    
    tickers = get_earnings_tickers(fmp_key)
    
    if tickers:
        df_ep = filter_us_ep_candidates(tickers)
        
        if not df_ep.empty:
            # 依 YoY 排序並取 Top 10，確保提示詞精練
            df_ep = df_ep.sort_values(by='YoY(%)', ascending=False).head(10)
            
            stock_list_str = ""
            for idx, row in df_ep.iterrows():
                stock_list_str += f"- ${row['Ticker']} {row['Name']} | YoY: {row['YoY(%)']}% | 市值: ${row['MarketCap(B)']}B | 均量: {row['AvgVol(K)']}K\n"
            
            discord_msg = f"🗽 **美股 NTRT 盤前雷達 ({today_str})** 🗽\n"
            discord_msg += "請複製以下提示詞，交由 AI 進行盤前質化決選：\n\n"
            discord_msg += "```text\n"
            discord_msg += "你是一位精通 StockBee Episodic Pivot (EP) 策略的美股頂尖交易員。\n"
            discord_msg += "請從以下「剛發布財報、營收暴增且平時被冷落」的美股初篩名單中，挑選出最具爆發潛力的 1~3 檔股票。\n\n"
            discord_msg += "【初篩名單 (已按 YoY 排序)】\n"
            discord_msg += stock_list_str + "\n"
            discord_msg += "【分析要求】\n"
            discord_msg += "請務必「聯網搜尋」名單上每家公司在過去 24 小時內發布的「Earnings Call (法說會) 逐字稿重點或財報新聞」。\n\n"
            discord_msg += "【EP 完美催化劑標準】\n"
            discord_msg += "1. 成長型 (Growth EP)：接獲新訂單，且「強力上修未來幾季的財測指引 (Guidance Raises)」。\n"
            discord_msg += "2. 轉機型 (Turnaround EP)：處於循環底部，財報顯示「由虧轉盈 (Inflection)」，這類股票適合做更長期的波段。\n"
            discord_msg += "3. 題材型 (Story EP)：獲得 FDA 批准、美國政府/國防部大單、或切入 AI 核心供應鏈。\n\n"
            discord_msg += "【美股專屬交易鐵律 (請在分析結果中標註提醒)】\n"
            discord_msg += "若該股票盤前跳空幅度大於 40% (Gap > 40%)，請標註「禁止 OPG 市價追高，需轉入延遲反應 (Delayed Reaction) 觀察池等待突破」。\n\n"
            discord_msg += "【輸出格式】\n"
            discord_msg += "直接回覆精煉後的 1~3 檔標的。標註 EP 類型，並用 100 字簡述你查到的「Earnings 催化劑亮點」。\n"
            discord_msg += "```"
            
            send_to_discord(discord_msg)
        else:
            send_to_discord(f"📊 **美股 NTRT 盤前雷達 ({today_str})**\n昨晚至今日盤前發布財報的公司中，無符合「YoY>39% + 市值<10B + 均量<1.5M」的量化標的。")
    else:
        print("今日查無財報發布數據。")
