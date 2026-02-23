import os
import time
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone
from io import StringIO  # 用來修復 pandas read_html 的報錯

def get_earnings_tickers_yahoo(start_date, end_date):
    """主引擎：加入 Cookie 預熱、完整現代瀏覽器偽裝與 StringIO 解析"""
    print(f"📥 [主引擎] 正在從 Yahoo Finance 抓取 {start_date} 至 {end_date} 的財報日曆...")
    tickers = set()
    
    # 建立 Session 來保存 Cookies，這是突破防火牆的關鍵
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
    }
    session.headers.update(headers)
    
    try:
        print("🍪 正在進行 Yahoo 伺服器 Cookie 預熱...")
        # 先訪問首頁獲取合法憑證
        session.get("https://finance.yahoo.com/", timeout=15)
        time.sleep(1.5) 
        
        dates_to_fetch = [start_date, end_date]
        
        for date_str in dates_to_fetch:
            url = f"https://finance.yahoo.com/calendar/earnings?day={date_str}"
            try:
                res = session.get(url, timeout=15)
                
                # 檢查是否被伺服器阻擋
                if "ApacheTrafficServer" in res.text or res.status_code != 200:
                    print(f"⚠️ Yahoo 伺服器仍阻擋連線 (Status: {res.status_code})")
                    continue
                    
                # 【關鍵修復】使用 StringIO 避免 pandas 2.1.0 以上版本報錯
                try:
                    dfs = pd.read_html(StringIO(res.text))
                    if dfs:
                        df = dfs[0]
                        if 'Symbol' in df.columns:
                            # 排除含有 . 的非美股代號
                            symbols = df[~df['Symbol'].str.contains(r'\.', na=False)]['Symbol'].unique().tolist()
                            tickers.update(symbols)
                except ValueError:
                    print(f"⚠️ Yahoo {date_str} 找不到財報表格 (可能當日無財報發布)。")
                    
            except Exception as e:
                print(f"⚠️ Yahoo {date_str} 日曆抓取失敗: {e}")
            
            time.sleep(2.5) 
            
    except Exception as e:
        print(f"⚠️ Yahoo 主引擎初始化失敗: {e}")
        
    if tickers:
        print(f"✅ [主引擎] 成功從 Yahoo 獲取 {len(tickers)} 檔財報代號。")
        return list(tickers)
        
    return None

def get_earnings_tickers_finnhub(api_key, start_date, end_date):
    """備援引擎：Finnhub JSON API (穩定、需免費 Key)"""
    print(f"🥷 [備援引擎] 啟動 Finnhub API 抓取財報日曆...")
    if not api_key:
        print("⚠️ 未設定 FINNHUB_API_KEY，跳過備援引擎。")
        return []
        
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={start_date}&to={end_date}&token={api_key}"
    try:
        res = requests.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            if 'earningsCalendar' in data:
                df = pd.DataFrame(data['earningsCalendar'])
                if not df.empty and 'symbol' in df.columns:
                    # 排除非美股
                    symbols = df[~df['symbol'].str.contains(r'\.', na=False)]['symbol'].unique().tolist()
                    print(f"✅ [備援引擎] 成功從 Finnhub 獲取 {len(symbols)} 檔財報代號。")
                    return symbols
        else:
            print(f"❌ Finnhub API 回應異常: {res.status_code}")
    except Exception as e:
        print(f"❌ Finnhub 抓取失敗: {e}")
        
    return []

def get_earnings_tickers(finnhub_key):
    """智慧切換：先用 Yahoo，失敗再用 Finnhub"""
    # 以 UTC-5 (美東時間) 為基準
    today = datetime.now(timezone.utc) - timedelta(hours=5) 
    start_date = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    end_date = today.strftime('%Y-%m-%d')
    
    # 1. 嘗試主引擎 (Yahoo)
    tickers = get_earnings_tickers_yahoo(start_date, end_date)
    
    # 2. 若主引擎全軍覆沒，啟動備援引擎 (Finnhub)
    if not tickers:
        print("⚠️ 主引擎無法取得資料，自動切換至備援引擎...")
        tickers = get_earnings_tickers_finnhub(finnhub_key, start_date, end_date)
        
    return tickers

def filter_us_ep_candidates(tickers, max_cap=10000000000, max_vol=1500000):
    """執行 yfinance 核心濾網：YoY > 39%、市值 < 10B、均量 < 1.5M"""
    print(f"🔍 開始執行營收 YoY 與冷落濾網，預計檢查 {len(tickers)} 檔股票...")
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
    """將結果推播至 Discord"""
    webhook_url = os.environ.get('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        print("⚠️ 未設定 DISCORD_WEBHOOK_URL，跳過推播。")
        return
        
    # 確保不會超過 Discord 字數限制
    if len(content) > 1950:
        content = content[:1950] + "\n...(名單過長已截斷)"
    requests.post(webhook_url, json={"content": content})
    print("✅ 成功發送至 Discord！")

if __name__ == "__main__":
    finnhub_key = os.environ.get('FINNHUB_API_KEY')
    today_str = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime('%Y-%m-%d')
    print(f"🚀 啟動美股 NTRT 盤前掃描 ({today_str})")
    
    # 雙引擎獲取名單
    tickers = get_earnings_tickers(finnhub_key)
    
    if tickers:
        df_ep = filter_us_ep_candidates(tickers)
        
        if not df_ep.empty:
            # 依 YoY 排序並取 Top 10，確保提示詞精練
            df_ep = df_ep.sort_values(by='YoY(%)', ascending=False).head(10)
            
            stock_list_str = ""
            for idx, row in df_ep.iterrows():
                stock_list_str += f"- ${row['Ticker']} {row['Name']} | YoY: {row['YoY(%)']}% | 市值: ${row['MarketCap(B)']}B | 均量: {row['AvgVol(K)']}K\n"
            
            # ===== 美股大師級 AI 提示詞組合 =====
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
        print("今日查無財報發布數據 (雙引擎皆未回傳資料)。")
