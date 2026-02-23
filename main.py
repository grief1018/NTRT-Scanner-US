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

def get_earnings_tickers_finnhub(api_key, start_
