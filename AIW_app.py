# ==========================================
# 파일명: AIW_app.py
# 목적: 세투연펀드 7기 리스크 관리 시스템
# ==========================================

import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="세투연펀드 7기 리스크 관리 시스템",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 세션 상태 초기화
today = datetime.today().date()
if 'target_date' not in st.session_state:
    st.session_state.target_date = today

st.title("📈 세투연펀드 7기 포트폴리오 관리 시스템")

# 달력 UI 배치
col1, col2 = st.columns([1, 4])
with col1:
    selected_date = st.date_input(
        "🗓️ 펀드 기준일 설정",
        value=st.session_state.target_date,
        max_value=today
    )

# 날짜 변경 시 메모리 초기화 및 재시작
if selected_date != st.session_state.target_date:
    st.session_state.target_date = selected_date
    if 'sim_df_portfolio' in st.session_state: del st.session_state['sim_df_portfolio']
    if 'sim_returns_df' in st.session_state: del st.session_state['sim_returns_df']
    st.rerun()

st.markdown(f"**현재 설정된 기준일:** {selected_date.strftime('%Y-%m-%d')} | **Fund:** 세투연 7기 Active Fund")
st.divider()

# 펀드 개요
st.subheader("📌 펀드 운용 목표")
st.info(
    "'벤치마크' 상회!!!"
)
st.markdown("<br>", unsafe_allow_html=True)

# 시스템 구성 가이드
st.subheader("🧭 시스템 구성")
c1, c2 = st.columns(2)

with c1:
    st.markdown("""
    ### 📊 1. 리스크 보고서 (Risk Report)
    좌측 메뉴의 `AIW risk report`를 클릭하세요.
    * **주간 컴플라이언스 점검:** 주식 비중, 개별종목 한도, 별도 자산 편입 룰 자동 감시
    * **핵심 리스크 지표 산출:** 10일 VaR, Expected Shortfall, MDD 추적
    """)

with c2:
    st.markdown("""
    ### 🕹️ 2. What-If 시뮬레이터 (What-If)
    좌측 메뉴의 `AIW whatif`를 클릭하세요.
    * **동적 종목 편입:** 티커 검색으로 신규 편입 후보 종목 실시간 연동
    * **최적 주식수 산출:** 벤치마크 변동성 제한을 준수하는 최적 주식수 자동 산출
    """)

st.divider()
st.caption("ⓒ 2026 세투연 펀드 7기. | Built for Fund Management. | Made by 김정원")

# 터미널 실행 안내문
if __name__ == '__main__':
    import sys
    if "streamlit" not in sys.argv[0].lower():
        print("\n" + "=".center(60, "="))
        print("\n아래 명령어를 드래그해서 복사(Ctrl+C)한 뒤, 터미널에 붙여넣기(Ctrl+V)하고 엔터를 치세요!\n")
        print(">>  streamlit run AIW_app.py  <<\n")
        print("=".center(60, "=") + "\n")
