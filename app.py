import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
import pytz
from st_aggrid import AgGrid, GridOptionsBuilder, ColumnsAutoSizeMode, JsCode

# Google API libraries
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

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
# Session State Initialization
# -----------------------------------------------------------------------------
for key in ['returns_df', 'scanned_message', 'scanned_status', 'bulk_message', 'bulk_status', 'missing_bulk_ids']:
    if key not in st.session_state:
        st.session_state[key] = None

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def get_current_ist_time():
    """Returns the current time in Indian Standard Time (IST)."""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist).strftime('%Y-%m-%d %I:%M:%S %p')

def load_data_from_gsheet(url):
    try:
        # Convert Google Sheet URL to CSV download URL
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if match:
            sheet_id = match.group(1)
            gid = "0"
            if "gid=" in url:
                gid = url.split("gid=")[1].split("&")[0]
            
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            df = pd.read_csv(csv_url)
        else:
            st.sidebar.error("❌ Invalid Google Sheet URL. Kripya link check karein.")
            return None
        
        df.columns = df.columns.str.strip()
        
        if 'Tracking ID' not in df.columns:
            st.sidebar.error("❌ 'Tracking ID' column Google Sheet mein nahi mila.")
            return None
                
        # "Received" Status ko explicitly text mein rakhna ("Received" or "Not Received")
        if 'Received' not in df.columns:
            df['Received'] = "Not Received"
        else:
            df['Received'] = df['Received'].apply(
                lambda x: "Received" if str(x).strip().lower() in ['true', 'received', 'yes'] else "Not Received"
            )
            
        # Timestamp column initialize
        if 'Received Timestamp' not in df.columns:
            df['Received Timestamp'] = ""
            
        df['Tracking ID'] = df['Tracking ID'].astype(str).str.strip().str.lower()
        
        # COLUMN REARRANGEMENT: Ensure 'Received' and 'Received Timestamp' are ALWAYS at the end (After AK column)
        all_cols = [c for c in df.columns if c not in ['Received', 'Received Timestamp']]
        all_cols.extend(['Received', 'Received Timestamp'])
        df = df[all_cols]
        
        return df
    except Exception as e:
        st.sidebar.error(f"File load karne mein error: {e}. Dhyan rakhein link 'Anyone with the link' par set ho.")
        return None

def sync_to_google_sheet(df, url):
    """Saves the updated DataFrame back to the live Google Sheet."""
    if not GSPREAD_AVAILABLE:
        return False, "Kripya 'gspread' aur 'google-auth' ko requirements.txt mein add karein."
        
    try:
        if "gcp_service_account" not in st.secrets:
            return False, "API Key missing! Kripya Streamlit Secrets mein GCP Service Account add karein."
            
        scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        client = gspread.authorize(creds)
        
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', url)
        if not match:
            return False, "Invalid Google Sheet URL"
            
        sheet_id = match.group(1)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.sheet1
        
        # FIX: Clean dataframe for Google Sheets (Int64 JSON error fix)
        df_filled = df.fillna("").astype(str)
        
        # Convert into a pure Python list of lists
        data_to_upload = [df_filled.columns.tolist()] + df_filled.values.tolist()
        
        # FIX FOR GSPREAD 6.0+: Specify range_name="A1" so it knows where to paste data
        worksheet.update(range_name="A1", values=data_to_upload)
        
        return True, "Success"
    except Exception as e:
        return False, f"Error details: {str(e)}"

def process_scan(tracking_id):
    df = st.session_state.get('returns_df')
    if df is None:
        st.error("Kripya pehle Google Sheet load karein.")
        return

    clean_id = str(tracking_id).strip().lower()
    if not clean_id:
        return

    mask = df['Tracking ID'] == clean_id
    if mask.any():
        row = df[mask].iloc[0]
        sku = row.get('SKU', 'N/A')
        qty = row.get('Quantity', 'N/A')
        
        if df.loc[mask, 'Received'].iloc[0] == "Received":
            st.session_state['scanned_status'] = 'warning'
            st.session_state['scanned_message'] = f"⚠️ Tracking ID '{tracking_id}' PEHLE SE received mark hai. (SKU: {sku} | Qty: {qty})"
        else:
            df.loc[mask, 'Received'] = "Received"
            df.loc[mask, 'Received Timestamp'] = get_current_ist_time()
            
            st.session_state['returns_df'] = df
            st.session_state['scanned_status'] = 'success'
            st.session_state['scanned_message'] = f"✅ Received Mark Ho Gaya: {tracking_id} | SKU: {sku} | Qty: {qty}"
    else:
        st.session_state['scanned_status'] = 'error'
        st.session_state['scanned_message'] = f"❌ Tracking ID '{tracking_id}' sheet mein nahi mila!"

def display_aggrid(df):
    default_cols = [
        'Order ID',  
        'Tracking ID',    
        'SKU',            
        'Quantity',       
        'Return Status',  
        'Return Type',    
        'Received',       
        'Received Timestamp'
    ]
    
    display_cols = [c for c in default_cols if c in df.columns]
    filtered_for_display = df[display_cols]
    
    gb = GridOptionsBuilder.from_dataframe(filtered_for_display)
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=50)
    gb.configure_default_column(filterable=True, sortable=True, resizable=True)
    
    row_style_jscode = JsCode("""
    function(params) {
        if (params.data.Received === "Received") {
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

def get_missing_ids_csv(missing_ids_list):
    df = pd.DataFrame({'Tracking ID Not Found': missing_ids_list})
    return df.to_csv(index=False).encode('utf-8')

def process_bulk_upload(bulk_file):
    df = st.session_state.get('returns_df')
    st.session_state['missing_bulk_ids'] = None
    
    if df is None:
        st.session_state['bulk_status'] = 'error'
        st.session_state['bulk_message'] = "Kripya sidebar se pehle Google Sheet load karein!"
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
            
        bulk_ids = set(bulk_df['Tracking ID'].dropna().astype(str).str.strip().str.lower().tolist())
        main_ids = set(df['Tracking ID'].astype(str).tolist())
        
        if not bulk_ids:
            st.session_state['bulk_status'] = 'error'
            st.session_state['bulk_message'] = "⚠️ Upload ki gayi file khaali hai."
            return
            
        missing_ids = list(bulk_ids - main_ids)
        st.session_state['missing_bulk_ids'] = missing_ids
        
        bulk_ids_list = list(bulk_ids)
        matches_mask = df['Tracking ID'].isin(bulk_ids_list)
        
        already_received = df[matches_mask & (df['Received'] == "Received")].shape[0]
        newly_received_mask = matches_mask & (df['Received'] == "Not Received")
        newly_received = df[newly_received_mask].shape[0]
        
        # Mark Received and Add Timestamp
        current_time = get_current_ist_time()
        df.loc[newly_received_mask, 'Received'] = "Received"
        df.loc[newly_received_mask, 'Received Timestamp'] = current_time
        
        st.session_state['returns_df'] = df
        
        not_found_count = len(missing_ids)
        
        st.session_state['bulk_status'] = 'success'
        st.session_state['bulk_message'] = f"✅ Bulk Update Pura Hua! \n\n🎯 Naye mark hue: **{newly_received}** \n⚠️ Pehle se mark the: **{already_received}** \n❌ Sheet mein nahi mile: **{not_found_count}**"
        
    except Exception as e:
        st.session_state['bulk_status'] = 'error'
        st.session_state['bulk_message'] = f"File process karne mein error: {e}"

# -----------------------------------------------------------------------------
# Sidebar
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Operations")
    st.markdown("**1. Master Google Sheet**")
    
    default_url = "https://docs.google.com/spreadsheets/d/1EUkC4MZAaIW5MIfYNT01nsYyttrL1Rp-a9Z2EsOU6us/edit?usp=sharing"
    gsheet_url = st.text_input("Google Sheet Link:", value=default_url)
    
    if st.button("🔄 Data Load Karein", type="primary"):
        if gsheet_url:
            with st.spinner("Google Sheets se data aa raha hai..."):
                loaded_df = load_data_from_gsheet(gsheet_url)
                if loaded_df is not None:
                    st.session_state['returns_df'] = loaded_df
                    st.success("✅ Data load ho gaya!")
                    st.rerun()
        else:
            st.warning("Kripya link daalein.")

    current_df = st.session_state.get('returns_df')
    
    if current_df is not None:
        st.divider()
        st.markdown("### ☁️ Sync & Save Data")
        
        if st.button("🚀 Live Sheet Mein Update Karein", use_container_width=True, type="primary"):
            with st.spinner("Google Sheet update ho rahi hai..."):
                success, msg = sync_to_google_sheet(current_df, gsheet_url)
                if success:
                    st.success("✅ Google Sheet update ho gayi!")
                else:
                    st.error(f"❌ Update fail hua: {msg}")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.info("Aap data local computer mein bhi download kar sakte hain:")
        
        excel_data = to_excel(current_df)
        st.download_button(label="📊 Updated Excel Download Karein", data=excel_data, file_name="updated_flipkart_returns.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
        
        st.divider()
        if st.button("🗑️ Sabhi Received Marks Clear Karein", use_container_width=True):
            current_df['Received'] = "Not Received"
            current_df['Received Timestamp'] = ""
            st.session_state['returns_df'] = current_df
            st.session_state['scanned_message'] = None
            st.session_state['bulk_message'] = None
            st.session_state['missing_bulk_ids'] = None
            st.rerun()

# -----------------------------------------------------------------------------
# Main Application Page
# -----------------------------------------------------------------------------
st.title("📦 Flipkart Returns Scanner")

main_df = st.session_state.get('returns_df')

if main_df is None:
    st.info("👈 Kripya sidebar mein 'Data Load Karein' par click karke shuru karein.")
else:
    total_count = len(main_df)
    received_count = (main_df['Received'] == "Received").sum()
    pending_count = total_count - received_count
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Returns", total_count)
    col2.metric("✅ Received", received_count)
    col3.metric("⏳ Pending", pending_count)
    
    st.divider()

    tab_scan, tab_bulk = st.tabs(["🎯 Single Scan", "📁 Bulk Upload"])
    
    # --- TAB 1: Single Scan ---
    with tab_scan:
        st.markdown('<p class="big-font">Tracking ID Scan Karein</p>', unsafe_allow_html=True)
        
        with st.form("scan_form", clear_on_submit=True):
            col_input, col_btn = st.columns([4, 1])
            with col_input:
                manual_tracking_id = st.text_input("Tracking ID", label_visibility="collapsed", placeholder="Yahan Tracking ID scan ya type karein...")
            with col_btn:
                submitted = st.form_submit_button("Received Mark Karein", use_container_width=True)
            
            if submitted and manual_tracking_id:
                process_scan(manual_tracking_id)

        msg = st.session_state.get('scanned_message')
        if msg:
            status = st.session_state.get('scanned_status', 'info')
            if status == 'success':
                st.success(msg)
            elif status == 'warning':
                st.warning(msg)
            else:
                st.error(msg)

        st.markdown("### 📊 Data Overview")
        display_aggrid(main_df)

    # --- TAB 2: BULK UPLOAD ---
    with tab_bulk:
        st.markdown("### 📥 Bulk Mark Returns")
        st.write("Agar aapke paas ek sath bahut saari Tracking IDs hain, toh is feature ka use karein.")
        
        st.markdown("**Step 1:** Niche se template download karein.")
        st.download_button(
            label="⬇️ Download Tracking ID Template",
            data=get_bulk_template_csv(),
            file_name="bulk_tracking_template.csv",
            mime="text/csv"
        )
        
        st.markdown("**Step 2:** File mein IDs paste karein.")
        
        st.markdown("**Step 3:** Bhari hui file yahan upload karein.")
        bulk_file = st.file_uploader("Upload Filled Template (.csv / .xlsx)", type=['csv', 'xlsx'])
        
        if st.button("🚀 Process Bulk Upload", type="primary"):
            if bulk_file is not None:
                process_bulk_upload(bulk_file)
            else:
                st.warning("Kripya pehle file upload karein.")
                
        # --- BULK UPLOAD MESSAGES & MISSING IDs DOWNLOAD ---
        bulk_msg = st.session_state.get('bulk_message')
        if bulk_msg:
            b_status = st.session_state.get('bulk_status', 'info')
            if b_status == 'success':
                st.success(bulk_msg)
                
                missing_ids = st.session_state.get('missing_bulk_ids')
                if missing_ids and len(missing_ids) > 0:
                    st.warning(f"⚠️ {len(missing_ids)} Tracking IDs sheet mein nahi mili. Unhe niche se download karein:")
                    st.download_button(
                        label="⬇️ Download Missing IDs (CSV)",
                        data=get_missing_ids_csv(missing_ids),
                        file_name="missing_tracking_ids.csv",
                        mime="text/csv",
                        type="secondary"
                    )
            else:
                st.error(bulk_msg)
