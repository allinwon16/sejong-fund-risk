# ==========================================
# 파일명: AIW_risk_engine.py
# 목적: 펀드 기초 데이터 수집 및 리스크 연산 코어 엔진
# ==========================================

import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import FinanceDataReader as fdr
import streamlit as st

# ==========================================
# 1. 포트폴리오 유니버스 및 컴플라이언스 룰
# ==========================================

PORTFOLIO = {
    "CASH": {"name": "현금", "quantity": 401364, "buy_price": 1, "sector": "현금"},
    "069500": {"name": "KODEX 200", "quantity": 111, "buy_price": 112254, "sector": "벤치마크"},
    "005930": {"name": "삼성전자", "quantity": 18, "buy_price": 269000, "sector": "IT/반도체"},
    "000660": {"name": "SK하이닉스", "quantity": 2, "buy_price": 1879000, "sector": "IT/반도체"},
    "086790": {"name": "하나금융지주", "quantity": 24, "buy_price": 133900, "sector": "금융/지주"},
    "049720": {"name": "고려신용정보", "quantity": 362, "buy_price": 9066, "sector": "금융/지주"},
    "411060": {"name": "ACE KRX금현물", "quantity": 124, "buy_price": 26565, "sector": "원자재"},
    "138910": {"name": "KODEX 구리선물(H)", "quantity": 160, "buy_price": 10330, "sector": "원자재"},
}

COMPLIANCE_RULES = {
    "MIN_STOCK_WEIGHT": 0.6,
    "MAX_STOCK_WEIGHT": 1.0,
    "MAX_CASH_WEIGHT": 0.4,
    "MIN_STOCK_COUNT": 3,
    "MAX_INDIV_WEIGHT": 0.4,
    "MAX_HEDGE_WEIGHT": 0.4,
    "MAX_OTHER_WEIGHT": 0.2
}

fallback_rf_rate = 0.0400

# ==========================================
# 2. 외부 데이터 수집 (Data Fetching)
# ==========================================

# 시계열 연동 시 프로그레스 바 실시간 연동
def fetch_historical_prices(portfolio_dict, start_date, end_date, p_bar=None, step=0, total=1):
    price_dict = {}
    for t in portfolio_dict:
        if t == "CASH": continue
        if p_bar:
            step += 1
            p_bar.progress(min(step / total, 0.9), text=f"과거 1년 데이터 연동 중... ({portfolio_dict[t]['name']})")
        try:
            df = fdr.DataReader(t, start_date, end_date)
            if df is not None and not df.empty and "Close" in df.columns:
                s = pd.to_numeric(df["Close"], errors="coerce").dropna()
                s.index = pd.to_datetime(s.index).normalize()
                price_dict[t] = s
        except Exception: pass
    return (pd.DataFrame(price_dict).sort_index().ffill() if price_dict else pd.DataFrame()), step

def fetch_benchmark_returns(start_date, end_date, ticker="069500"):
    try:
        df = fdr.DataReader(ticker, start_date, end_date)
        if df is not None and not df.empty and "Close" in df.columns:
            s = pd.to_numeric(df["Close"], errors="coerce").dropna()
            s.index = pd.to_datetime(s.index).normalize()
            return s.sort_index().pct_change().dropna()
    except Exception: pass
    return pd.Series(dtype=float)

def fetch_risk_free_rate(target_date_str):
    try:
        target_dt = pd.to_datetime(target_date_str)
        start_date = (target_dt - timedelta(days=15)).strftime('%Y-%m-%d')
        
        for t in ['KR3YT=RR', 'KR3YT=X']:
            try:
                df = fdr.DataReader(t, start_date, end=target_date_str)
                if df is not None and not df.empty:
                    rate = float(df.iloc[-1]['Close']) / 100
                    if rate > 0: return rate
            except Exception: continue
    except Exception: pass
    return fallback_rf_rate

# ==========================================
# 3. 퀀트 통계 및 성과 지표 산출 모듈
# ==========================================

def align_two_series(s1, s2):
    if s1 is None or s2 is None or len(s1) == 0 or len(s2) == 0: return pd.Series(dtype=float), pd.Series(dtype=float)
    aligned = pd.concat([s1, s2], axis=1).dropna()
    return (aligned.iloc[:, 0], aligned.iloc[:, 1]) if len(aligned) >= 2 else (pd.Series(dtype=float), pd.Series(dtype=float))

def calculate_beta(returns, benchmark):
    stock_ret, bench_ret = align_two_series(returns, benchmark)
    if stock_ret.empty: return np.nan
    bench_var = bench_ret.var()
    return stock_ret.cov(bench_ret) / bench_var if bench_var != 0 else np.nan

def calculate_sharpe_ratio(returns, risk_free_rate=0.0):
    if returns is None or returns.empty: return np.nan
    excess = returns - (risk_free_rate / 252)
    ann_vol = returns.std() * np.sqrt(252)
    return (excess.mean() * 252) / ann_vol if ann_vol != 0 else np.nan

def calculate_sortino_ratio(returns, risk_free_rate=0.0):
    if returns is None or returns.empty: return np.nan
    excess = returns - (risk_free_rate / 252)
    downside_std = np.sqrt(np.mean(np.minimum(0, excess)**2)) * np.sqrt(252)
    return (excess.mean() * 252) / downside_std if downside_std != 0 else np.nan

def calculate_tracking_error(portfolio_returns, benchmark_returns, periods=252):
    port_ret, bench_ret = align_two_series(portfolio_returns, benchmark_returns)
    return np.std(port_ret - bench_ret, ddof=1) * np.sqrt(periods) if not port_ret.empty else np.nan

def calculate_var_es(std, days=10, confidence=0.95):
    if pd.isna(std) or std == 0: return 0.0, 0.0
    z_var, z_es = (1.65, 2.06) if confidence == 0.95 else (2.33, 2.66)
    return std * np.sqrt(days) * z_var, std * np.sqrt(days) * z_es

def calculate_mdd(cumulative_returns):
    if cumulative_returns is None or cumulative_returns.empty: return np.nan
    rolling_max = cumulative_returns.cummax()
    return ((cumulative_returns - rolling_max) / rolling_max).min()

def calculate_weekly_mdd(returns):
    if returns is None or returns.empty: return np.nan
    weekly_nav = (1 + returns).cumprod().resample("W-FRI").last().dropna()
    return ((weekly_nav - weekly_nav.cummax()) / weekly_nav.cummax()).min() if len(weekly_nav) >= 2 else np.nan

def calculate_var_contribution(returns_df, weights, confidence=0.95):
    if returns_df is None or returns_df.empty: return None
    z = 1.65 if confidence == 0.95 else 2.33
    cov_matrix = returns_df.cov()
    w_arr = np.array(weights)
    
    port_vol = np.sqrt(np.dot(w_arr.T, np.dot(cov_matrix, w_arr)))
    if port_vol == 0 or np.isnan(port_vol): return None

    marginal_var = np.dot(cov_matrix, w_arr) / port_vol
    comp_var = w_arr * marginal_var * z
    tot_comp_var = comp_var.sum()
    
    contrib_pct = comp_var / tot_comp_var if tot_comp_var != 0 and not np.isnan(tot_comp_var) else np.repeat(np.nan, len(comp_var))

    return pd.DataFrame({"Weight": w_arr, "VaR Contribution": comp_var, "Contribution %": contrib_pct, "Marginal VaR": marginal_var * z * 0.01}, index=returns_df.columns)

# ==========================================
# 4. 리스크 판별 및 종합 리스크 연산
# ==========================================

def get_status(val, warn, danger, is_lower_better=True):
    if pd.isna(val): return "⚪️ N/A"
    return ("🟢 정상" if val < warn else "🟡 경계" if val < danger else "🔴 위험") if is_lower_better else ("🟢 정상" if val > warn else "🟡 경계" if val > danger else "🔴 위험")

def get_beta_status(val):
    if pd.isna(val): return "⚪️ N/A"
    return "🔴 위험" if val < 0.5 or val > 1.3 else "🟡 경계" if 0.5 <= val < 0.6 or 1.2 < val <= 1.3 else "🟢 정상"

def generate_risk_report(portfolio_df, returns_df, benchmark_returns, rf_rate):
    risk_data = []
    for _, r in portfolio_df.iterrows():
        t, n, w, roi = r['티커'], r['종목명'], r['비중'], r['수익률']
        if t == "CASH":
            risk_data.append({"종목명": t, "이름": n, "비중": w, "수익률": roi, "표준편차(일간)": 0.0, "표준편차(연환산)": 0.0, "베타": 0.0, "10일VaR(95%)": 0.0, "10일ES(95%)": 0.0, "샤프지수": np.nan, "소티노지수": np.nan, "MDD": 0.0, "주간 MDD": 0.0})
            continue
            
        if t not in returns_df.columns or len(returns_df[t].dropna()) < 20:
            risk_data.append({"종목명": t, "이름": n, "비중": w, "수익률": roi, "표준편차(일간)": np.nan, "표준편차(연환산)": np.nan, "베타": np.nan, "10일VaR(95%)": np.nan, "10일ES(95%)": np.nan, "샤프지수": np.nan, "소티노지수": np.nan, "MDD": np.nan, "주간 MDD": np.nan})
            continue
            
        ret = returns_df[t].dropna()
        std, beta = ret.std(), calculate_beta(ret, benchmark_returns)
        var, es = calculate_var_es(std)
        risk_data.append({"종목명": t, "이름": n, "비중": w, "수익률": roi, "표준편차(일간)": std, "표준편차(연환산)": std * np.sqrt(252), "베타": beta, "10일VaR(95%)": var, "10일ES(95%)": es, "샤프지수": calculate_sharpe_ratio(ret, rf_rate), "소티노지수": calculate_sortino_ratio(ret, rf_rate), "MDD": calculate_mdd((1 + ret).cumprod()), "주간 MDD": calculate_weekly_mdd(ret)})
    return pd.DataFrame(risk_data)

def calculate_portfolio_beta(portfolio_df, returns_df, benchmark_returns):
    stock_df = portfolio_df[portfolio_df['티커'] != 'CASH']
    if stock_df.empty or benchmark_returns.empty or stock_df['비중'].sum() == 0: return 0.0
    
    betas, weights = [], []
    for _, r in stock_df.iterrows():
        t = r['티커']
        if t in returns_df.columns:
            b = calculate_beta(returns_df[t].dropna(), benchmark_returns)
            betas.append(b if not np.isnan(b) else 0)
            weights.append(r['비중'])

    return np.dot(np.array(weights) / stock_df['비중'].sum(), betas) * stock_df['비중'].sum()

def calculate_portfolio_risks(portfolio_df, returns_df, benchmark_returns, rf_rate):
    stock_df = portfolio_df[portfolio_df['티커'] != 'CASH']
    valid_tickers = [t for t in stock_df['티커'] if t in returns_df.columns]
    
    cash_w = portfolio_df.loc[portfolio_df['티커'] == 'CASH', '비중'].sum() if 'CASH' in portfolio_df['티커'].values else 0.0
    stock_w = 1.0 - cash_w
    
    tot_buy = (portfolio_df['매수가'] * portfolio_df['수량']).sum()
    tot_eval = portfolio_df['평가금액'].sum()
    tot_roi = (tot_eval - tot_buy) / tot_buy if tot_buy > 0 else 0.0
    
    if not valid_tickers or returns_df.empty:
        return {"총수익률": tot_roi, "주식비중": stock_w, "현금비중": cash_w}

    w_arr = stock_df.set_index('티커').loc[valid_tickers, '비중'].values
    w_arr = w_arr / w_arr.sum() 
    
    port_ret_series = pd.Series(np.dot(returns_df[valid_tickers].fillna(0), w_arr) * stock_w, index=returns_df.index)
    port_std_daily = np.sqrt(np.dot(w_arr.T, np.dot(returns_df[valid_tickers].cov(), w_arr))) * stock_w
    
    port_var, port_es = calculate_var_es(port_std_daily)
    port_mdd, port_wmdd = calculate_mdd((1 + port_ret_series).cumprod()), calculate_weekly_mdd(port_ret_series)
    port_beta = calculate_portfolio_beta(portfolio_df, returns_df, benchmark_returns)
    port_weekly_ret = (1 + port_ret_series.tail(5)).prod() - 1 if len(port_ret_series) >= 5 else np.nan
    bm_weekly_ret = (1 + benchmark_returns.tail(5)).prod() - 1 if len(benchmark_returns) >= 5 else np.nan

    comp_results, vio_cnt = [], 0
    c = COMPLIANCE_RULES

    def add_comp(i, lim, v_str, cond):
        nonlocal vio_cnt
        if not cond: vio_cnt += 1
        comp_results.append({"관리 항목": i, "관리 기준": lim, "현재 수치": v_str, "상태": "🟢 준수" if cond else "🔴 위반"})

    add_comp("주식 비중", f"{c['MIN_STOCK_WEIGHT']*100:.0f}% ~ {c['MAX_STOCK_WEIGHT']*100:.0f}%", f"{stock_w*100:.1f}%", c['MIN_STOCK_WEIGHT'] <= stock_w <= c['MAX_STOCK_WEIGHT'])
    add_comp("현금 및 예수금 한도", f"{c['MAX_CASH_WEIGHT']*100:.0f}% 이하", f"{cash_w*100:.1f}%", cash_w <= c['MAX_CASH_WEIGHT'])
    add_comp("개별종목 편입 수", f"최소 {c['MIN_STOCK_COUNT']}종목 이상", f"{len(valid_tickers)} 종목", len(valid_tickers) >= c['MIN_STOCK_COUNT'])

    k200_etfs = ['069500', '102110', '148020', '152100', '213610', '227830', '278530', '278540', '292750', '315930', '379660', '433330']
    max_w, max_n = 0, "없음"
    hedge_w, other_w = 0.0, 0.0
    etf_brands = ['KODEX', 'TIGER', 'KBSTAR', 'ACE', 'ARIRANG', 'KOSEF', 'HANARO']

    for _, r in stock_df.iterrows():
        t, n, w = r['티커'], r['종목명'].upper(), r['비중']
        if t not in k200_etfs and w > max_w: max_w, max_n = w, r['종목명']
        if "레버리지" in n or "인버스" in n or "2X" in n: hedge_w += w
        elif t not in k200_etfs and (any(b in n for b in etf_brands) or "채권" in n): other_w += w
            
    add_comp("개별종목 편입 한도", f"{c['MAX_INDIV_WEIGHT']*100:.0f}% 이하", f"최대 {max_n} ({max_w*100:.1f}%)" if max_w > 0 else "해당 없음", max_w <= c['MAX_INDIV_WEIGHT'])
    add_comp("헤지 목적 ETF 한도", f"{c['MAX_HEDGE_WEIGHT']*100:.0f}% 이하", f"{hedge_w*100:.1f}%", hedge_w <= c['MAX_HEDGE_WEIGHT'])
    add_comp("별도 자산(기타 ETF/채권)", f"{c['MAX_OTHER_WEIGHT']*100:.0f}% 이하", f"{other_w*100:.1f}%", other_w <= c['MAX_OTHER_WEIGHT'])
    comp_results.append({"관리 항목": "실물/해외채권 직접투자", "관리 기준": "금지", "현재 수치": "위반 없음", "상태": "🟢 준수"})

    # VaR 쏠림
    var_df = calculate_var_contribution(returns_df, w_arr)
    conc_stat, sec_conc_stat, sec_var_df = "🟢 정상", "🟢 정상", pd.DataFrame()

    if var_df is not None and not var_df.empty:
        eval_stk = var_df[var_df.index != '069500'].copy()
        if not eval_stk.empty:
            m_pct = eval_stk["Contribution %"].abs().max()
            conc_stat = "🔴 위험" if m_pct > 0.50 else "🟡 경계" if m_pct > 0.40 else "🟢 정상"

        var_df["Sector"] = var_df.index.map({r['티커']: r['섹터'] for _, r in stock_df.iterrows()})
        sec_var_df = var_df.groupby("Sector").sum(numeric_only=True)
        tot_var = sec_var_df["VaR Contribution"].sum()
        
        if tot_var != 0: sec_var_df["Contribution %"] = sec_var_df["VaR Contribution"] / tot_var
        eval_sec = sec_var_df[sec_var_df.index != '벤치마크'].copy()
        
        if not eval_sec.empty:
            ms_pct = eval_sec["Contribution %"].abs().max()
            sec_conc_stat = "🔴 위험" if ms_pct > 0.60 else "🟡 경계" if ms_pct > 0.50 else "🟢 정상"

    bm_var, bm_es = calculate_var_es(benchmark_returns.std())
    bm_mdd, bm_wmdd = calculate_mdd((1 + benchmark_returns).cumprod()), calculate_weekly_mdd(benchmark_returns)
    
    return {
        "총수익률": tot_roi, "포트폴리오_베타": port_beta, "10일VaR": port_var, "10일ES": port_es,
        "포트폴리오_주간수익률": port_weekly_ret, 
        "벤치마크_주간수익률": bm_weekly_ret,
        "표준편차(일간)": port_std_daily, "표준편차(연환산)": port_std_daily * np.sqrt(252),
        "MDD": port_mdd, "주간MDD": port_wmdd, "트래킹에러": calculate_tracking_error(port_ret_series, benchmark_returns),
        "샤프지수": calculate_sharpe_ratio(port_ret_series, rf_rate), "소티노지수": calculate_sortino_ratio(port_ret_series, rf_rate),
        "주식비중": stock_w, "현금비중": cash_w, "포트폴리오_수익률_시리즈": port_ret_series,
        "벤치마크_샤프": calculate_sharpe_ratio(benchmark_returns, rf_rate), "벤치마크_소티노": calculate_sortino_ratio(benchmark_returns, rf_rate),
        "벤치마크_10일VaR": bm_var, "벤치마크_10일ES": bm_es, "벤치마크_MDD": bm_mdd, "벤치마크_주간MDD": bm_wmdd,
        "베타_상태": get_beta_status(port_beta), "10일VaR_상태": get_status(port_var, bm_var * 1.1, bm_var * 1.2),
        "10일ES_상태": get_status(port_es, bm_es * 1.1, bm_es * 1.2),
        "MDD_상태": get_status(port_mdd, bm_mdd * 1.1, bm_mdd * 1.2, is_lower_better=False),
        "주간MDD_상태": get_status(port_wmdd, bm_wmdd * 1.15, bm_wmdd * 1.3, is_lower_better=False),
        "컴플라이언스_위반건수": vio_cnt, "컴플라이언스_상세": comp_results,
        "VaR_기여도_DF": var_df, "쏠림_상태": conc_stat,
        "섹터_VaR_기여도_DF": sec_var_df, "섹터_쏠림_상태": sec_conc_stat
    }

# ==========================================
# 5. 캐싱 데이터 로드 (Central Data Hub)
# ==========================================

@st.cache_data(ttl=3600, show_spinner=False)
def get_engine_data(target_date_str):
    target_dt = pd.to_datetime(target_date_str)
    
    # 프로그레스 바 UI 초기화
    ui_placeholder = st.empty()
    p_bar = ui_placeholder.progress(0, text="금융 데이터 서버 연결 중...")
    
    stock_count = len([k for k in PORTFOLIO if k != 'CASH'])
    total_steps = (stock_count * 2) + 2
    step = 0
    
    CURRENT_PRICES = {}
    for t in PORTFOLIO:
        if t == "CASH": continue
        step += 1
        p_bar.progress(min(step / total_steps, 0.9), text=f"최신 주가 파싱 중... ({PORTFOLIO[t]['name']})")
        try:
            df = fdr.DataReader(t, start=target_dt - timedelta(days=10), end=target_dt)
            if not df.empty: CURRENT_PRICES[t] = float(df['Close'].iloc[-1])
            time.sleep(0.05)
        except Exception: CURRENT_PRICES[t] = None

    port_summary = []
    for t, info in PORTFOLIO.items():
        n, q, bp, sec = info["name"], info["quantity"], info["buy_price"], info.get("sector", "기타")
        if t == "CASH":
            cp, val, roi = 1.0, float(q), 0.0
        else:
            cp = CURRENT_PRICES.get(t, 0)
            val, roi = (q * cp, (cp - bp) / bp) if cp else (0, 0.0)
            
        port_summary.append({"티커": t, "종목명": n, "섹터": sec, "매수가": bp, "현재가": cp, "수량": q, "평가금액": val, "수익률": roi})
        
    df_port = pd.DataFrame(port_summary)
    tot_val = df_port['평가금액'].sum()
    df_port['비중'] = df_port['평가금액'] / tot_val if tot_val > 0 else 0

    start_date = target_dt - timedelta(days=365)
    # 시계열 연동 시 프로그레스 바 실시간 업데이트
    price_df, step = fetch_historical_prices(PORTFOLIO, start_date, target_dt, p_bar, step, total_steps)
    ret_df = price_df.pct_change().dropna(how='all') if not price_df.empty else pd.DataFrame()
    
    step += 1
    p_bar.progress(min(step / total_steps, 0.95), text="벤치마크 지수 연동 중...")
    bm_ret = fetch_benchmark_returns(start_date, target_dt)
    
    step += 1
    p_bar.progress(0.99, text="무위험수익률(국고채) 연동 중...")
    rf_rate = fetch_risk_free_rate(target_date_str)
    
    p_bar.progress(1.0, text="데이터 연동 완료! 엔진 가동!")
    time.sleep(0.3)
    ui_placeholder.empty() # 연동 종료 후 프로그레스 바 숨김
    
    return df_port, ret_df, bm_ret, rf_rate
