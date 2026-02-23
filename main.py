import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone

def get_earnings_tickers_fmp(api_key, start_date, end_date):
    """主引擎：透過 FMP API 獲取財報代號"""
    url = f"https://financialmodelingprep.com/api/v3/earning_calendar?from={start_date}&to={end_date}&apikey={api_key}"
    print(f"📥 [主引擎] 正在向 FMP 請求 {start_date} 至 {end_date} 的美股財報日曆...")
    
    res = requests.get(url, timeout=15)
    if res.status_code == 403:
        print("⚠️ FMP 回傳 403 Forbidden。可能是 API Key 無效、未驗證 Email，或免費額度受限。")
        return None
    elif res.status_code != 200:
        print(f"⚠️ FMP API 回應異常: {res.status_code}")
        return None
        
    df = pd.DataFrame(res.json())
    if df.empty:
        return []
        
    df = df[~df['symbol'].str.contains(r'\.')]
    return df['symbol'].unique().tolist()

def get_earnings_tickers_yahoo(start_date, end_date):
    """備援引擎：透過 Yahoo Finance 獲取財報代號"""
    print(f"🥷 [備援引擎] 啟動 Yahoo Finance 財報日曆抓取...")
    try:
        # yfinance 雖然沒有直接的區間日曆，但可以透過 research 或第三方開源解析
        # 這裡我們使用一個免 API Key 的備用公開端點 (Yahoo/Finnhub 結構)
        # 為了穩定性，我們直接抓取今天市場上的熱門財報清單
        # 注意：此處作為 403 的應急備案
        url = "https://finance.yahoo.com/calendar/earnings"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        res = requests.get(url, headers=headers, timeout=15)
        dfs = pd.read_html(res.text)
        
        if dfs:
            df = dfs[0]
            if 'Symbol' in df.columns:
                tickers = df['Symbol'].unique().tolist()
                print(f"✅ [備援引擎] 成功獲取 {len(tickers)} 檔財報代號。")
                return tickers
    except Exception as e:
        print(f"❌ Yahoo 備援抓取失敗: {e}")
    return []

def get_earnings_tickers(api_key):
    """整合雙引擎獲取名單"""
    # 修正 DeprecationWarning，改用 timezone.utc
    today = datetime.now(timezone.utc) - timedelta(hours=5) 
    start_date = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    # 優先嘗試 FMP
    tickers = get_earnings_tickers_fmp(api_key, start_date, end_date)
    
    # 若 FMP 失敗 (回傳 None)，則啟動備援引擎
    if tickers is None:
        tickers = get_earnings_tickers_yahoo(start_date, end_date)
        
    return tickers

def filter_us_ep_candidates(tickers, max_cap=10000000000, max_vol=1500000):
    print(f"🔍 開始執行營收 YoY 與冷落濾網，檢查 {len(tickers)} 檔股票...")
    ep_list = []
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            rev_growth = info.get('revenueGrowth')
            if rev_growth is None or rev_growth < 0.39:
                continue
                
            market_cap = info.get('marketCap')
            if market_cap is None or market_cap > max_cap:
                continue
                
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
        
    today_str = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime('%Y-%m-%d')
    print(f"🚀 啟動美股 NTRT 盤前掃描 ({today_str})")
    
    tickers = get_earnings_tickers(fmp_key)
    
    if tickers:
        df_ep = filter_us_ep_candidates(tickers)
        
        if not df_ep.empty:
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
