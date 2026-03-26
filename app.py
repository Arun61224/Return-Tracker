import streamlit as st
import pandas as pd
import io
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, JsCode

# -----------------------------------------------------------------------------
# Configuration & Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Flipkart Returns Scanner",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .big-font { font-size: 24px !important; font-weight: bold; }
    .scan-box { margin-bottom: 20px; }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Bulletproof Session State Initialization
# -----------------------------------------------------------------------------
# Ye loop ensure karega ki keys hamesha exist karein, chahe app refresh ho
for key in ['returns_df', 'scanned_message', 'scanned_status']:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def load_data(file):
    try:
        try:
            df = pd.read_excel(file, sheet_name="1-25 Flipkart Return")
        except ValueError:
            df = pd.read_excel(file, sheet_name=0)
        
        df.columns = df.columns.str.strip()
        
        if 'Tracking ID' not in df.columns:
            st.sidebar.error("❌ 'Tracking ID' column not found in the uploaded file.")
            return None
                
        if 'Received' not in df.columns:
            df['Received'] = False
        else:
            df['Received'] = df['Received'].apply(lambda x: True if str(x).lower() == 'true' else False)
            
        df['Tracking ID'] = df['Tracking ID'].astype(str).str.strip().str.lower()
        
        return df
    except Exception as e:
        st.sidebar.error(f"Error loading file: {e}")
        return None

def process_scan(tracking_id):
    df = st.session_state.get('returns_df')
    if df is None:
        st.error("Please upload a file first.")
        return

    clean_id = str(tracking_id).strip().lower()
    if not clean_id:
        return

    mask = df['Tracking ID'] == clean_id
    if mask.any():
        row = df[mask].iloc[0]
        sku = row.get('SKU', 'N/A')
        qty = row.get('Quantity', 'N/A')
        
        if df.loc[mask, 'Received'].iloc[0] == True:
            st.session_state['scanned_status'] = 'warning'
            st.session_state['scanned_message'] = f"⚠️ Tracking ID '{tracking_id}' is ALREADY marked as received. (SKU: {sku} | Qty: {qty})"
        else:
            df.loc[mask, 'Received'] = True
            st.session_state['returns_df'] = df
            st.session_state['scanned_status'] = 'success'
            st.session_state['scanned_message'] = f"✅ Marked Received: {tracking_id} | SKU: {sku} | Qty: {qty}"
    else:
        st.session_state['scanned_status'] = 'error'
        st.session_state['scanned_message'] = f"❌ Tracking ID '{tracking_id}' not found in uploaded sheet!"

def display_aggrid(df):
    # Only the columns you specifically requested + Received
    default_cols = [
        'Order Item ID',  # C
        'Tracking ID',    # E
        'SKU',            # H
        'Quantity',       # L
        'Return Status',  # U
        'Return Type',    # W
        'Received'        
    ]
    
    display_cols = [c for c in default_cols if c in df.columns]
    filtered_for_display = df[display_cols]
    
    gb = GridOptionsBuilder.from_dataframe(filtered_for_display)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_default_column(filterable=True, sortable=True, resizable=True)
    
    row_style_jscode = JsCode("""
    function(params) {
        if (params.data.Received === true || params.data.Received === 'true') {
            return {
                'color': '#0f5132',
                'backgroundColor': '#d1e7dd'
            }
        }
    };
    """)
    gb.configure_grid_options(getRowStyle=row_style_jscode)
    grid_options = gb.build()

    AgGrid(
        filtered_for_display,
        gridOptions=grid_options,
        enable_enterprise_modules=False,
        allow_unsafe_jscode=True,
        update_mode="NO_UPDATE",
        columns_auto_size_mode=ColumnsAutoSizeMode.FIT_CONTENTS,
        theme='streamlit' 
    )

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Updated Returns')
    return output.getvalue()

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Operations")
    uploaded_file = st.file_uploader("Upload Returns Excel (.xlsx)", type=['xlsx', 'xls'])
    
    # Safe check for df
    current_df = st.session_state.get('returns_df')
    
    if uploaded_file is not None and current_df is None:
        with st.spinner("Loading Data..."):
            loaded_df = load_data(uploaded_file)
            if loaded_df is not None:
                st.session_state['returns_df'] = loaded_df
                st.success("File loaded successfully!")
                st.rerun()

    # Re-fetch df after potential upload
    current_df = st.session_state.get('returns_df')
    
    if current_df is not None:
        st.divider()
        st.markdown("### Data Management")
        
        csv = current_df.to_csv(index=False).encode('utf-8')
        st.download_button(label="💾 Save Current Data as CSV", data=csv, file_name="returns_backup.csv", mime="text/csv", use_container_width=True)
        
        excel_data = to_excel(current_df)
        st.download_button(label="📊 Download Updated Excel", data=excel_data, file_name="updated_flipkart_returns.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")
        
        st.divider()
        if st.button("🗑️ Clear All Received Marks", use_container_width=True):
            current_df['Received'] = False
            st.session_state['returns_df'] = current_df
            st.session_state['scanned_message'] = None
            st.rerun()

# -----------------------------------------------------------------------------
# Main Application Page
# -----------------------------------------------------------------------------
st.title("📦 Flipkart Returns Scanner - Panipat / Malur / Bhiwandi")

main_df = st.session_state.get('returns_df')

if main_df is None:
    st.info("👈 Please upload your Flipkart Returns Excel file in the sidebar to begin.")
else:
    # Metrics
    total_count = len(main_df)
    received_count = main_df['Received'].sum()
    pending_count = total_count - received_count
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Returns", total_count)
    col2.metric("✅ Received", received_count)
    col3.metric("⏳ Pending", pending_count)
    
    st.divider()

    tab_scan, tab_all = st.tabs(["🎯 Scan & Mark Received", "📋 All Returns Data"])
    
    # --- TAB 1: Scan & Mark Received ---
    with tab_scan:
        st.markdown('<p class="big-font">Scan Tracking ID</p>', unsafe_allow_html=True)
        
        with st.form("scan_form", clear_on_submit=True):
            col_input, col_btn = st.columns([4, 1])
            with col_input:
                manual_tracking_id = st.text_input("Tracking ID", label_visibility="collapsed", placeholder="Scan or type Tracking ID here...")
            with col_btn:
                submitted = st.form_submit_button("Mark as Received", use_container_width=True)
            
            if submitted and manual_tracking_id:
                process_scan(manual_tracking_id)
                st.rerun()

        # SAFE DISPLAY LOGIC - No Error Possible Here
        msg = st.session_state.get('scanned_message')
        if msg:
            status = st.session_state.get('scanned_status', 'info')
            if status == 'success':
                st.success(msg)
            elif status == 'warning':
                st.warning(msg)
            else:
                st.error(msg)

        st.markdown("### Recent Data Overview")
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            pending_only = st.checkbox("Show Pending Only", value=False, key="scan_pending")
        with f_col2:
            search_query = st.text_input("🔍 Quick Search (Tracking ID / SKU)", key="scan_search")

        filtered_df = main_df.copy()
        if pending_only:
            filtered_df = filtered_df[filtered_df['Received'] == False]
        if search_query:
            search_query = search_query.lower()
            mask = (
                filtered_df['Tracking ID'].astype(str).str.lower().str.contains(search_query) |
                filtered_df.get('SKU', pd.Series(dtype=str)).astype(str).str.lower().str.contains(search_query)
            )
            filtered_df = filtered_df[mask]

        display_aggrid(filtered_df)

    # --- TAB 2: All Returns ---
    with tab_all:
        st.markdown("### Master Returns Dataset")
        
        f2_col1, f2_col2 = st.columns(2)
        with f2_col1:
            all_pending_only = st.checkbox("Show Pending Only", value=False, key="all_pending")
        with f2_col2:
            all_search_query = st.text_input("🔍 Quick Search (Tracking ID / SKU)", key="all_search")

        filtered_all_df = main_df.copy()
        if all_pending_only:
            filtered_all_df = filtered_all_df[filtered_all_df['Received'] == False]
        if all_search_query:
            all_search_query = all_search_query.lower()
            mask2 = (
                filtered_all_df['Tracking ID'].astype(str).str.lower().str.contains(all_search_query) |
                filtered_all_df.get('SKU', pd.Series(dtype=str)).astype(str).str.lower().str.contains(all_search_query)
            )
            filtered_all_df = filtered_all_df[mask2]
            
        display_aggrid(filtered_all_df)
