import streamlit as st
from datetime import datetime
import pandas as pd

# Page config
st.set_page_config(
    page_title="Live Auction System - UI Preview",
    page_icon="🔨",
    layout="wide"
)

# Mock data
mock_products = [
    {"id": 1, "name": "Vintage Watch", "base_price": 150.00, "image": "https://via.placeholder.com/200x150"},
    {"id": 2, "name": "Antique Vase", "base_price": 200.00, "image": "https://via.placeholder.com/200x150"},
    {"id": 3, "name": "Rare Book", "base_price": 75.00, "image": "https://via.placeholder.com/200x150"}
]

mock_auctions = [
    {"code": "AUC-A1B2", "product": "Vintage Watch", "current_bid": 175.00, "bidder": "Alice", "time_left": "1:23"},
    {"code": "AUC-C3D4", "product": "Antique Vase", "current_bid": 250.00, "bidder": "Bob", "time_left": "0:45"}
]

# Initialize session state
if 'role' not in st.session_state:
    st.session_state.role = None
if 'username' not in st.session_state:
    st.session_state.username = None

# Sidebar for role selection
st.sidebar.title("🎭 Role Selection")
role = st.sidebar.selectbox("Select Role", ["Login", "Admin", "Seller", "Buyer"])

if role != "Login":
    st.session_state.role = role
    st.session_state.username = f"demo_{role.lower()}"

# Main content based on role
if st.session_state.role == "Admin":
    st.title("🔧 Admin Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Server Control")
        server_status = st.selectbox("Server Status", ["Running", "Stopped"])
        if server_status == "Running":
            st.success("✅ Auction Server is running")
            if st.button("Stop Server"):
                st.warning("Server stopped (demo)")
        else:
            st.error("❌ Auction Server is stopped")
            if st.button("Start Server"):
                st.success("Server started (demo)")
    
    with col2:
        st.subheader("System Stats")
        st.metric("Active Auctions", len(mock_auctions))
        st.metric("Total Users", 25)
        st.metric("Server Uptime", "2h 15m")
    
    st.subheader("📊 Closed Auctions")
    closed_data = {
        "Auction Code": ["AUC-X1Y2", "AUC-Z3W4"],
        "Product": ["Old Painting", "Silver Coin"],
        "Winner": ["Charlie", "Diana"],
        "Final Bid": [300.00, 125.00]
    }
    st.dataframe(pd.DataFrame(closed_data))

elif st.session_state.role == "Seller":
    st.title("💼 Seller Dashboard")
    
    tab1, tab2 = st.tabs(["Start Auction", "My Auctions"])
    
    with tab1:
        st.subheader("🏷️ Product Catalog")
        
        cols = st.columns(3)
        for i, product in enumerate(mock_products):
            with cols[i % 3]:
                st.image(product["image"], width=150)
                st.write(f"**{product['name']}**")
                st.write(f"Base Price: ${product['base_price']}")
                if st.button(f"Start Auction", key=f"start_{product['id']}"):
                    st.success(f"Auction started for {product['name']} (demo)")
    
    with tab2:
        st.subheader("📈 My Active Auctions")
        auction_data = {
            "Code": ["AUC-A1B2"],
            "Product": ["Vintage Watch"],
            "Current Bid": [175.00],
            "Bidder": ["Alice"],
            "Time Left": ["1:23"]
        }
        st.dataframe(pd.DataFrame(auction_data))

elif st.session_state.role == "Buyer":
    st.title("🛒 Buyer Dashboard")
    
    tab1, tab2 = st.tabs(["Join Auction", "My Bids"])
    
    with tab1:
        st.subheader("🔍 Join Auction")
        auction_code = st.text_input("Enter Auction Code", placeholder="AUC-XXXX")
        if st.button("Join Auction"):
            if auction_code:
                st.success(f"Joined auction {auction_code} (demo)")
            else:
                st.error("Please enter auction code")
        
        st.subheader("🔥 Live Auctions")
        for auction in mock_auctions:
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
                with col1:
                    st.write(f"**{auction['code']}**")
                    st.write(auction['product'])
                with col2:
                    st.metric("Current Bid", f"${auction['current_bid']}")
                with col3:
                    st.write(f"Leading: {auction['bidder']}")
                    st.write(f"⏰ {auction['time_left']}")
                with col4:
                    if st.button("Join", key=f"join_{auction['code']}"):
                        st.success(f"Joined {auction['code']} (demo)")
                st.divider()
    
    with tab2:
        st.subheader("💰 Bidding Interface")
        selected_auction = st.selectbox("Select Auction", [a['code'] for a in mock_auctions])
        bid_amount = st.number_input("Bid Amount", min_value=0.01, step=0.01)
        if st.button("Place Bid"):
            st.success(f"Bid of ${bid_amount} placed on {selected_auction} (demo)")

else:
    # Login page
    st.title("🔨 Live Auction System")
    st.subheader("Welcome to the Live Auction Platform")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔑 Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            st.info("Use the sidebar to preview different roles")
    
    with col2:
        st.subheader("📝 Register")
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        role_select = st.selectbox("Role", ["Buyer", "Seller"])
        if st.button("Register"):
            st.info("Registration demo - use sidebar for role preview")

# Footer
st.markdown("---")
st.markdown("**Note:** This is a UI preview only. No actual functionality is connected.")