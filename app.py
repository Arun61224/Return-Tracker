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
for key in ['returns_df', 'scanned_message', 'scanned_status', 'bulk_message', 'bulk_status']:
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
            st.sidebar.error("❌ 'Tracking ID' column not found in the uploaded master file.")
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
        st.error("Please upload the main file first.")
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

def get_bulk_template_csv():
    df = pd.DataFrame(columns=['Tracking ID'])
    return df.to_csv(index=False).encode('utf-8')

def process_bulk_upload(bulk_file):
    df = st.session_state.get('returns_df')
    if df is None:
        st.session_state['bulk_status'] = 'error'
        st.session_state['bulk_message'] = "Pehle sidebar mein Master Excel file upload karein!"
        return

    try:
        if bulk_file.name.endswith('.csv'):
            bulk_df = pd.read_csv(bulk_file)
        else:
            bulk_df = pd.read_excel(bulk_file)
            
        if 'Tracking ID' not in bulk_df.columns:
            st.session_state['bulk_status'] = 'error'
            st.session_state['bulk_message'] = "❌ Template mein 'Tracking ID' column nahi mila."
            return
            
        bulk_ids = bulk_df['Tracking ID'].dropna().astype(str).str.strip().str.lower().tolist()
        
        if not bulk_ids:
            st.session_state['bulk_status'] = 'error'
            st.session_state['bulk_message'] = "⚠️ File empty hai, koi Tracking ID nahi mili."
            return
            
        main_ids = df['Tracking ID']
        matches = main_ids.isin(bulk_ids)
        
        already_received = df[matches & (df['Received'] == True)].shape[0]
        newly_received = df[matches & (df['Received'] == False)].shape[0]
        
        df.loc[matches, 'Received'] = True
        st.session_state['returns_df'] = df
        
        total_unique_bulk = len(set(bulk_ids))
        found_in_master = df[matches]['Tracking ID'].nunique()
        not_found = total_unique_bulk - found_in_master
        
        st.session_state['bulk_status'] = 'success'
        st.session_state['bulk_message'] = f"✅ Bulk Update Complete! \n\n🎯 Naye mark hue: **{newly_received}** \n⚠️ Pehle se mark the: **{already_received}** \n❌ Sheet mein nahi mile: **{not_found}**"
        
    except Exception as e:
        st.session_state['bulk_status'] = 'error'
        st.session_state['bulk_message'] = f"Error processing file: {e}"

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Operations")
    st.markdown("**1. Upload Master Returns Data**")
    uploaded_file = st.file_uploader("Upload Returns Excel (.xlsx)", type=['xlsx', 'xls'], key="master_upload")
    
    current_df = st.session_state.get('returns_df')
    
    if uploaded_file is not None and current_df is None:
        with st.spinner("Loading Data..."):
            loaded_df = load_data(uploaded_file)
            if loaded_df is not None:
                st.session_state['returns_df'] = loaded_df
                st.success("Master File loaded successfully!")
                st.rerun()

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
            st.session_state['bulk_message'] = None
            st.rerun()

# -----------------------------------------------------------------------------
# Main Application Page
# -----------------------------------------------------------------------------
st.title("📦 Flipkart Returns Scanner")

main_df = st.session_state.get('returns_df')

if main_df is None:
    st.info("👈 Please upload your MAIN Flipkart Returns Excel file in the sidebar to begin.")
else:
    total_count = len(main_df)
    received_count = main_df['Received'].sum()
    pending_count = total_count - received_count
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Returns", total_count)
    col2.metric("✅ Received", received_count)
    col3.metric("⏳ Pending", pending_count)
    
    st.divider()

    # Sirf 2 Tabs ab
    tab_scan, tab_bulk = st.tabs(["🎯 Single Scan", "📁 Bulk Upload"])
    
    # --- TAB 1: Single Scan ---
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
        display_aggrid(main_df)

    # --- TAB 2: BULK UPLOAD ---
    with tab_bulk:
        st.markdown("### 📥 Bulk Mark Returns as Received")
        st.write("Agar aapke paas bahut saare Tracking IDs hain jo ek sath mark karne hain, toh is feature ka use karein.")
        
        st.markdown("**Step 1:** Niche di gayi template download karein.")
        st.download_button(
            label="⬇️ Download Tracking ID Template (CSV)",
            data=get_bulk_template_csv(),
            file_name="bulk_tracking_template.csv",
            mime="text/csv"
        )
        
        st.markdown("**Step 2:** Us template file mein apne saare Tracking IDs paste karke save karein.")
        
        st.markdown("**Step 3:** Bhari hui template ko yahan upload karein.")
        bulk_file = st.file_uploader("Upload Filled Template (.csv / .xlsx)", type=['csv', 'xlsx'])
        
        if st.button("🚀 Process Bulk Upload", type="primary"):
            if bulk_file is not None:
                process_bulk_upload(bulk_file)
                st.rerun()
            else:
                st.warning("Please upload a file first.")
                
        bulk_msg = st.session_state.get('bulk_message')
        if bulk_msg:
            b_status = st.session_state.get('bulk_status', 'info')
            if b_status == 'success':
                st.success(bulk_msg)
            else:
                st.error(bulk_msg)
