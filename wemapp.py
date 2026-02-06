import streamlit as st
import pandas as pd
from datetime import timedelta, date
import io
import re

# --- 設定網頁標題 ---
st.set_page_config(page_title="宿舍費用分攤系統 (民國年版)", layout="wide")
st.title("🏠 宿舍費用分攤系統 (民國年版)")
st.markdown("### 採用「總人次加權平均法」")
st.caption("🇹🇼 已切換為民國年輸入模式 (例如：112/09/01)")

# --- 工具函式：民國年字串 轉 西元 Date物件 ---
def parse_roc_date(date_str):
    """
    將民國年字串 (112/09/01, 112-09-01, 112.09.01, 1120901) 轉換為 datetime.date
    """
    try:
        if pd.isna(date_str) or str(date_str).strip() == "":
            return None
        
        date_str = str(date_str).strip()
        
        # 使用正規表達式切分 (支援 / - . 或無分隔符)
        match = re.match(r'(\d{2,3})[/\-\.]?(\d{1,2})[/\-\.]?(\d{1,2})', date_str)
        
        if match:
            roc_year, month, day = map(int, match.groups())
            # 民國轉西元
            gregorian_year = roc_year + 1911
            return date(gregorian_year, month, day)
        else:
            return None
    except:
        return None

# --- 工具函式：西元 Date物件 轉 民國年字串 (Excel輸出用) ---
def date_to_roc_str(d):
    if isinstance(d, date):
        return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"
    return ""

# --- 核心運算邏輯函數 ---
def calculate_costs(df_bills, df_students):
    # 0. 資料前處理：將民國年字串轉換為西元日期物件
    try:
        # 轉換帳單日期
        df_bills['start_dt'] = df_bills['開始日期(民國)'].apply(parse_roc_date)
        df_bills['end_dt'] = df_bills['結束日期(民國)'].apply(parse_roc_date)
        
        # 轉換學生日期
        df_students['start_dt'] = df_students['入住日期(民國)'].apply(parse_roc_date)
        df_students['end_dt'] = df_students['退宿日期(民國)'].apply(parse_roc_date)

        # 檢查是否有轉換失敗的日期
        if df_bills['start_dt'].isnull().any() or df_bills['end_dt'].isnull().any():
            raise ValueError("帳單資料中有無法辨識的日期格式，請檢查是否為 112/09/01 格式。")
        if df_students['start_dt'].isnull().any() or df_students['end_dt'].isnull().any():
            raise ValueError("學生資料中有無法辨識的日期格式，請檢查是否為 112/09/01 格式。")

    except Exception as e:
        return None, None, None, [f"日期格式錯誤: {str(e)}"]

    # 1. 初始化容器
    unique_students = df_students['學生姓名'].unique()
    cost_details = {name: {bill: 0.0 for bill in df_bills['帳單名稱']} for name in unique_students}
    day_details = {name: {bill: 0 for bill in df_bills['帳單名稱']} for name in unique_students}
    total_costs = {name: 0.0 for name in unique_students}
    daily_log = []

    # 2. 遍歷每一張帳單
    for index, bill in df_bills.iterrows():
        bill_name = bill['帳單名稱']
        amount = bill['金額']
        b_start = bill['start_dt'] # 使用轉換後的西元日期
        b_end = bill['end_dt']
        
        temp_student_days = {name: 0 for name in unique_students}
        total_person_days = 0 

        # 3. 計算每位學生重疊天數
        for s_idx, student in df_students.iterrows():
            s_name = student['學生姓名']
            s_start = student['start_dt']
            s_end = student['end_dt']
            
            overlap_start = max(b_start, s_start)
            overlap_end = min(b_end, s_end)
            
            if overlap_start <= overlap_end:
                days = (overlap_end - overlap_start).days + 1
            else:
                days = 0
            
            temp_student_days[s_name] += days
            total_person_days += days
            
        # 4. 記錄天數
        for s_name in unique_students:
            day_details[s_name][bill_name] = temp_student_days[s_name]

        # 5. 分攤費用
        if total_person_days > 0:
            cost_per_person_day = amount / total_person_days
            for s_name, days in temp_student_days.items():
                if days > 0:
                    share = days * cost_per_person_day
                    total_costs[s_name] += share
                    cost_details[s_name][bill_name] += share
        else:
            daily_log.append(f"帳單【{bill_name}】期間無人住宿 (總人次為0)，金額 {amount} 無法分攤")

    # 6. 整理輸出
    results_cost = []
    for name in unique_students:
        row = {'學生姓名': name, '應付總額': round(total_costs[name], 0)}
        for bill_name in df_bills['帳單名稱']:
            row[bill_name] = round(cost_details[name][bill_name], 0)
        results_cost.append(row)
    
    results_days = [] # 顯示用
    results_days_raw = [] # 數值用
    for name in unique_students:
        row_view = {'學生姓名': name}
        row_raw = {'學生姓名': name}
        for bill_name in df_bills['帳單名稱']:
            days = day_details[name][bill_name]
            row_view[bill_name] = f"{days} 天"
            row_raw[bill_name] = days
        results_days.append(row_view)
        results_days_raw.append(row_raw)
            
    return pd.DataFrame(results_cost), pd.DataFrame(results_days), pd.DataFrame(results_days_raw), daily_log

# --- 側邊欄 ---
with st.sidebar:
    st.header("使用說明")
    st.info("""
    1. **日期格式**：請輸入民國年，例如 `112/09/01` 或 `1130101`。
    2. **多時段**：同一位學生若有不同住宿時段，請新增一行輸入相同姓名即可。
    """)

# --- 主畫面：資料輸入區 ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. 帳單資料輸入 (民國年)")
    # 預設資料改為民國年字串
    default_bills = pd.DataFrame({
        '帳單名稱': ['水費', '電費9月', '電費10月', '瓦斯費'],
        '金額': [450, 3000, 2800, 1150],
        '開始日期(民國)': ['112/09/01', '112/09/01', '112/10/01', '112/09/05'],
        '結束日期(民國)': ['112/10/31', '112/09/30', '112/10/31', '112/11/04']
    })
    # 使用 TextColumn 讓使用者輸入字串
    edited_bills = st.data_editor(
        default_bills, 
        num_rows="dynamic",
        column_config={
            "金額": st.column_config.NumberColumn(format="$%d"),
            "開始日期(民國)": st.column_config.TextColumn(help="請輸入格式: 112/01/01"),
            "結束日期(民國)": st.column_config.TextColumn(help="請輸入格式: 112/01/01")
        },
        key="bills_editor"
    )

with col2:
    st.subheader("2. 學生住宿資料輸入 (民國年)")
    # 預設資料改為民國年字串
    default_students = pd.DataFrame({
        '學生姓名': ['小明', '小華', '小美', '小明'],
        '入住日期(民國)': ['112/09/01', '112/09/15', '112/09/01', '112/10/20'],
        '退宿日期(民國)': ['112/09/30', '112/11/04', '112/10/15', '112/11/04']
    })
    edited_students = st.data_editor(
        default_students, 
        num_rows="dynamic",
        column_config={
            "入住日期(民國)": st.column_config.TextColumn(help="請輸入格式: 112/01/01"),
            "退宿日期(民國)": st.column_config.TextColumn(help="請輸入格式: 112/01/01")
        },
        key="students_editor"
    )

st.divider()

# --- 計算按鈕 ---
if st.button("🚀 開始計算分攤費用", type="primary"):
    if edited_bills.empty or edited_students.empty:
        st.error("請輸入完整的帳單與學生資料！")
    else:
        # 執行運算
        df_cost, df_days_view, df_days_raw, logs = calculate_costs(edited_bills, edited_students)
        
        if df_cost is None:
            # 發生轉換錯誤 (logs 裡裝的是錯誤訊息)
            st.error(logs[0])
        else:
            st.success("計算完成！")
            
            tab1, tab2, tab3 = st.tabs(["💰 費用分攤表", "📅 天數統計表", "📝 異常日誌"])
            
            with tab1:
                st.dataframe(df_cost.style.highlight_max(axis=0, subset=['應付總額'], color='#FFDDC1'), use_container_width=True)
                
            with tab2:
                st.dataframe(df_days_view, use_container_width=True)

            with tab3:
                if logs:
                    for log in logs:
                        st.write(log)
                else:
                    st.write("無異常紀錄。")

            # --- Excel 匯出 (包含將結果轉回民國年字串的邏輯，如果需要的話) ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_cost.to_excel(writer, index=False, sheet_name='費用分攤表')
                df_days_raw.to_excel(writer, index=False, sheet_name='天數統計表')
                # 原始資料直接輸出使用者輸入的民國年字串，保持原樣
                edited_bills.to_excel(writer, index=False, sheet_name='原始帳單資料')
                edited_students.to_excel(writer, index=False, sheet_name='原始學生資料')
            
            excel_data = output.getvalue()

            st.download_button(
                label="📥 下載 Excel 報表",
                data=excel_data,
                file_name=f"宿舍費用分攤表_民國年版.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )