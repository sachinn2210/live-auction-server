import streamlit as st
import subprocess
from pathlib import Path
import psutil
import mysql.connector
import hashlib
import pandas as pd
from datetime import datetime
import time
from auction_listener import finalize_mongo_auction
import socket
import random
import string
import json
import os
import queue
from streamlit_autorefresh import st_autorefresh
from pathlib import Path
# Use environment variables or config file
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "123456"),
    "database": os.getenv("DB_NAME", "auction_system")
}

# Make paths configurable
CSV_PATH = Path(r"D:\TY SEM1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-\train.csv")
SERVER_EXE = Path(r"D:\TY SEM1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-\Server\AuctionServer.exe")

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000

# ============= DATABASE FUNCTIONS =============
def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def user_exists(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def validate_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user = cursor.fetchone()
    conn.close()
    if user and user["password_hash"] == hash_password(password):
        return user
    return None

def register_user(username, password, role):
    if user_exists(username):
        st.error("Username already exists.")
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
        (username, hash_password(password), role)
    )
    conn.commit()
    conn.close()
    st.success("Registration successful. Please login.")
    return True

# ============= SERVER CONTROL =============
def is_server_running():
    for process in psutil.process_iter(['pid', 'name']):
        try:
            if process.info['name'] and "AuctionServer.exe" in process.info['name']:
                return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    return False

def kill_server():
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            if proc.info['name'] and "AuctionServer.exe" in proc.info['name']:
                proc.kill()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    st.success("Auction Server stopped successfully.")

# ============= PRODUCTS =============
def load_products():
    if not CSV_PATH.exists():
        st.error(f"CSV file not found: {CSV_PATH}")
        return pd.DataFrame()
    
    sample = open(CSV_PATH, 'r', encoding='utf-8', errors='ignore').readline()
    sep = '\t' if '\t' in sample else ','
    df = pd.read_csv(CSV_PATH, sep=sep, encoding='utf-8', engine='python')
    df = df.rename(columns=str.strip)
    cols = [c for c in ['sample_id', 'catalog_content', 'image_link', 'price'] if c in df.columns]
    return df[cols].dropna().head(15)

# ============= AUCTIONS =============
def generate_auction_code():
    return "AUC-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def insert_auction(product_id, name, image, price, duration_minutes=2):
    conn = get_db_connection()
    cursor = conn.cursor()
    auction_code = generate_auction_code()
    
    cursor.execute(
        """INSERT INTO auctions
           (product_id, product_name, image_link, base_price, status, start_time,
            duration_minutes, created_by, auction_code)
           VALUES (%s,%s,%s,%s,'active', NOW(), %s, %s, %s)""",
        (int(product_id), name[:255], image, float(price), int(duration_minutes),
         st.session_state.username, auction_code)
    )
    conn.commit()
    conn.close()
    st.session_state.last_auction_code = auction_code

def close_expired_auctions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='active'")
    active_auctions = cursor.fetchall()
    now = datetime.now()
    
    for auction in active_auctions:
        start_time = auction["start_time"]
        duration = auction["duration_minutes"]
        elapsed = (now - start_time).total_seconds() / 60
        
        if elapsed >= duration:
            final_bid = auction.get("current_bid", auction["base_price"])
            winner = auction.get("current_bidder", "No Bids")
            cursor.execute("""
                UPDATE auctions 
                SET status='closed', end_time=%s, final_bid=%s, winner=%s
                WHERE id=%s
            """, (now, final_bid, winner, auction["id"]))
            print(f"Closed Auction {auction['id']} | Winner: {winner} | Final Bid: {final_bid}")
            
            try:
                finalize_mongo_auction(auction["product_id"], winner, final_bid)
            except Exception as e:
                print(f"Error finalizing MongoDB auction: {e}")
    
    conn.commit()
    conn.close()

def get_active_auctions():
    close_expired_auctions()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='active'")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_closed_auctions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='closed' ORDER BY end_time DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_seller_auctions(username):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT * FROM auctions 
        WHERE created_by = %s 
        ORDER BY start_time DESC
    """, (username,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_auction_by_id(auction_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE id=%s", (auction_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# ============= TCP CLIENT MANAGEMENT (THREAD-SAFE) =============
class TCPClient:
    """Thread-safe TCP client wrapper for auction bidding"""
    
    def __init__(self):
        self.socket = None
        self.connected = False
        self.message_queue = queue.Queue()
        self.error = None
    
    def connect(self, username: str, auction_code: str):
        """Connect to TCP server and send JOIN message"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((SERVER_HOST, SERVER_PORT))
            self.socket.settimeout(None)
            
            # Send JOIN message
            join_msg = f"{username}|{auction_code}|JOIN\n"
            self.socket.sendall(join_msg.encode())
            
            self.connected = True
            self.error = None
            return True, None
            
        except Exception as e:
            self.connected = False
            self.error = str(e)
            if self.socket:
                self.socket.close()
            return False, str(e)
    
    def send_bid(self, bid_amount: float, username: str, auction_code: str):
        """Send bid to TCP server"""
        if not self.connected or not self.socket:
            return False, "Not connected to server"
        
        try:
            bid_msg = f"{username}|{auction_code}|{bid_amount}\n"
            self.socket.sendall(bid_msg.encode())
            return True, None
        except Exception as e:
            self.connected = False
            return False, str(e)
    
    def disconnect(self):
        """Properly disconnect from server"""
        if self.socket:
            try:
                self.socket.sendall(b"LEAVE\n")
                self.socket.close()
            except:
                pass
        self.connected = False
        self.socket = None

# ============= SESSION STATE HELPERS =============
def init_tcp_client():
    """Initialize TCP client in session state"""
    if 'tcp_client' not in st.session_state:
        st.session_state.tcp_client = TCPClient()

def cleanup_tcp_client():
    """Clean up TCP client connection"""
    if 'tcp_client' in st.session_state:
        st.session_state.tcp_client.disconnect()
        del st.session_state.tcp_client

# ============= STREAMLIT UI =============
st.set_page_config(page_title="Live Auction Dashboard", layout="centered")
st.markdown("<h1 style='text-align: center;'> Live Auction Management Console</h1>", unsafe_allow_html=True)
st.divider()

# Initialize session state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.selected_auction = None
    st.session_state.in_auction_room = False
    st.session_state.cached_auction = None
    st.session_state.last_bid_time = 0

# ============= LOGIN/REGISTER =============
if not st.session_state.logged_in:
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login to Your Account")
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login"):
            user = validate_user(username, password)
            if user:
                st.session_state.logged_in = True
                st.session_state.role = user["role"]
                st.session_state.username = user["username"]
                st.success(f"Welcome {user['username']} ({user['role']})!")
                st.rerun()
            else:
                st.error("Invalid username or password.")
    
    with tab2:
        st.subheader("Create New Account")
        new_user = st.text_input("Username", key="reg_user")
        new_pass = st.text_input("Password", type="password", key="reg_pass")
        role = st.selectbox("Role", ["Admin", "Seller", "Buyer"])
        if st.button("Register"):
            if new_user and new_pass:
                register_user(new_user, new_pass, role)
            else:
                st.warning("Please fill all fields.")

# ============= LOGGED IN USERS =============
else:
    role = st.session_state.role
    username = st.session_state.username
    st.sidebar.title(f"Welcome, {username}")
    
    # Navigation
    if role == "Admin":
        page = st.sidebar.radio("Go to", ["Server Control", "Bid History", "Closed Auctions", "Logout"])
    elif role == "Seller":
        page = st.sidebar.radio("Go to", ["Products", "My Auctions", "Logout"])
    elif role == "Buyer":
        page = st.sidebar.radio("Go to", ["Active Auctions", "Logout"])
    
    # ============= SELLER - PRODUCTS =============
    if role == "Seller" and page == "Products":
        st.header(" Product Catalog")
        products = load_products()
        
        if products.empty:
            st.warning("No products available.")
        else:
            duration = st.number_input("Auction Duration (minutes):", min_value=1, max_value=60, value=2)
            
            for _, row in products.iterrows():
                with st.container(border=True):
                    cols = st.columns([1, 3])
                    with cols[0]:
                        st.image(row["image_link"], width=150)
                    with cols[1]:
                        title = str(row["catalog_content"]).splitlines()[0]
                        st.markdown(f"**{title}**")
                        st.write(f"Price: ${row['price']}")
                        if st.button(f"Start Auction", key=f"start_{row['sample_id']}"):
                            insert_auction(row["sample_id"], row["catalog_content"], 
                                         row["image_link"], row["price"], duration)
                            st.success(f"Auction started for {row['sample_id']} lasting {duration} minute(s).")
                            st.info(f"Auction Code: **{st.session_state.last_auction_code}** — share this with buyers!")
                            st.rerun()
    
    # ============= ADMIN - SERVER CONTROL =============
    elif role == "Admin" and page == "Server Control":
        st.header("Server Control Panel (Admin)")
        if is_server_running():
            st.success("Server is active.")
            if st.button("Stop Server"):
                kill_server()
                st.rerun()
        else:
            st.warning("Server not running.")
            if st.button("Start Server"):
                if not SERVER_EXE.exists():
                    st.error(f"Server executable not found: {SERVER_EXE}")
                else:
                    try:
                        subprocess.Popen([str(SERVER_EXE)], cwd=str(SERVER_EXE.parent),
                                       creationflags=subprocess.CREATE_NEW_CONSOLE)
                        st.success("Auction Server launched successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to start server: {e}")
    
    # ============= ADMIN - CLOSED AUCTIONS =============
    elif role == "Admin" and page == "Closed Auctions":
        st.header("Closed Auctions")
        closed_auctions = get_closed_auctions()
        
        if not closed_auctions:
            st.info("No closed auctions yet.")
        else:
            for a in closed_auctions:
                with st.container(border=True):
                    cols = st.columns([1, 3])
                    with cols[0]:
                        st.image(a["image_link"], width=150)
                    with cols[1]:
                        st.markdown(f"**{a['product_name']}**")
                        st.write(f"Final Bid: **${a['final_bid'] or a['base_price']}**")
                        st.write(f"Winner: **{a['winner']}**")
                        st.write(f"Ended: {a['end_time']}")
    
    # ============= BUYER - ACTIVE AUCTIONS LIST =============
    elif role == "Buyer" and page == "Active Auctions" and not st.session_state.get("in_auction_room", False):
        # Slower refresh for auction list (10 seconds)
        st_autorefresh(interval=10000, key="auction_list_refresh")
        
        st.header(" Join or Browse Active Auctions")
        
        # Join by code
        st.subheader("Join Auction via Code")
        code_input = st.text_input("Enter Auction Code (e.g., AUC-1A2B)")
        if st.button("Join Auction via Code"):
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM auctions WHERE auction_code=%s AND status='active'", (code_input,))
            auction = cursor.fetchone()
            conn.close()
            
            if auction:
                st.session_state.selected_auction = auction["id"]
                st.session_state.in_auction_room = True
                st.rerun()
            else:
                st.error("Invalid or closed auction code.")
        
        st.divider()
        
        # Browse active auctions
        st.subheader("Live Auctions")
        auctions = get_active_auctions()
        
        if not auctions:
            st.info("No active auctions right now. Please check back later.")
        else:
            for a in auctions:
                start = a["start_time"]
                duration = a["duration_minutes"]
                
                if start:
                    elapsed = (datetime.now() - start).total_seconds()
                    remaining = max(0, duration * 60 - elapsed)
                    mins, secs = divmod(int(remaining), 60)
                    timer = f"{mins:02d}:{secs:02d}"
                else:
                    timer = "Unknown"
                
                with st.container(border=True):
                    cols = st.columns([1, 3])
                    with cols[0]:
                        st.image(a["image_link"], width=150)
                    with cols[1]:
                        st.markdown(f"**{a['product_name']}**")
                        st.write(f" Auction Code: **{a['auction_code']}**")
                        st.write(f"Base Price: ${a['base_price']}")
                        st.write(f"Current Bid: **${a.get('current_bid', a['base_price'])}**")
                        st.write(f"Highest Bidder: **{a.get('current_bidder', 'No bids yet')}**")
                        st.write(f" Time Remaining: **{timer}**")
                        
                        if st.button(f"Join Auction #{a['id']}", key=f"join_{a['id']}"):
                            st.session_state.selected_auction = a['id']
                            st.session_state.in_auction_room = True
                            st.rerun()
    
    # ============= BUYER - AUCTION ROOM =============
    elif role == "Buyer" and st.session_state.in_auction_room and st.session_state.selected_auction:
        # Medium refresh for auction room (3 seconds for DB updates)
        st_autorefresh(interval=3000, key="auction_room_refresh")
        
        # Initialize TCP client
        init_tcp_client()
        
        # Fetch fresh auction data from database
        auction = get_auction_by_id(st.session_state.selected_auction)
        
        if not auction:
            st.error("Auction not found or has been closed.")
            if st.button("Back to Active Auctions"):
                cleanup_tcp_client()
                st.session_state.in_auction_room = False
                st.session_state.selected_auction = None
                st.session_state.cached_auction = None
                st.rerun()
        
        elif auction.get('status') == 'closed':
            st.warning("This auction has ended.")
            st.write(f"**Final Bid:** ${auction.get('final_bid', auction['base_price'])}")
            st.write(f"**Winner:** {auction.get('winner', 'No winner')}")
            if st.button("Back to Active Auctions"):
                cleanup_tcp_client()
                st.session_state.in_auction_room = False
                st.session_state.selected_auction = None
                st.session_state.cached_auction = None
                st.rerun()
        
        else:
            # Connect to TCP server if not connected
            tcp_client = st.session_state.tcp_client
            if not tcp_client.connected:
                success, error = tcp_client.connect(username, auction["auction_code"])
                if not success:
                    st.error(f"Connection failed: {error}")
                    st.info("Make sure the Auction Server is running.")
                    if st.button("Retry Connection"):
                        st.rerun()
                    if st.button("Back to Active Auctions"):
                        cleanup_tcp_client()
                        st.session_state.in_auction_room = False
                        st.session_state.selected_auction = None
                        st.rerun()
                else:
                    st.success(f"Connected to auction {auction['auction_code']}!")
            
            # Display auction room UI
            if tcp_client.connected:
                st.header(f"Auction Room — {auction['product_name']}")
                
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    st.image(auction["image_link"], width=200)
                
                with col2:
                    st.write(f"**Base Price:** ${auction['base_price']}")
                    
                    # Current bid handling
                    current_bid = auction.get("current_bid") or auction["base_price"]
                    current_bidder = auction.get("current_bidder") or "No bids yet"
                    
                    # Time remaining
                    start_time = auction.get("start_time")
                    duration = auction.get("duration_minutes", 0)
                    if start_time:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        remaining = max(0, duration * 60 - elapsed)
                        mins, secs = divmod(int(remaining), 60)
                        timer_display = f"{mins:02d}:{secs:02d}"
                        
                        if remaining < 30:
                            st.error(f"Time Remaining: **{timer_display}** - HURRY!")
                        elif remaining < 60:
                            st.warning(f"Time Remaining: **{timer_display}**")
                        else:
                            st.info(f"Time Remaining: **{timer_display}**")
                    else:
                        st.write("Time Remaining: Unknown")
                    
                    st.write(f"**Current Bid:** ${current_bid}")
                    st.write(f"**Highest Bidder:** {current_bidder}")
                
                st.divider()
                
                # Bidding section
                st.subheader("Place Your Bid")
                
                min_bid = float(current_bid) + 1.0
                
                # Use form to prevent auto-refresh from clearing input
                with st.form(key="bid_form", clear_on_submit=True):
                    bid_value = st.number_input(
                        "Enter your bid amount",
                        min_value=min_bid,
                        value=min_bid,
                        format="%.2f",
                        help=f"Minimum bid: ${min_bid}"
                    )
                    
                    submitted = st.form_submit_button("🔨 Place Bid", type="primary", use_container_width=True)
                    
                    if submitted:
                        # Prevent rapid bid submissions
                        current_time = time.time()
                        if current_time - st.session_state.last_bid_time < 1:
                            st.warning("Please wait a moment before placing another bid.")
                        else:
                            success, error = tcp_client.send_bid(bid_value, username, auction["auction_code"])
                            if success:
                                st.success(f"Bid of ${bid_value} sent to server!")
                                st.session_state.last_bid_time = current_time
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"Failed to send bid: {error}")
                                # Try to reconnect
                                cleanup_tcp_client()
                                st.rerun()
                
                # Leave auction button
                if st.button("Leave Auction", use_container_width=True):
                    cleanup_tcp_client()
                    st.session_state.in_auction_room = False
                    st.session_state.selected_auction = None
                    st.session_state.cached_auction = None
                    st.rerun()
    
    # ============= ADMIN - BID HISTORY =============
    elif role == "Admin" and page == "Bid History":
        st.header(" Detailed Bid History (MongoDB)")
        
        try:
            from pymongo import MongoClient
            client = MongoClient("mongodb://localhost:27017")
            db = client["auction_data"]
            history = list(db["auction_history"].find().sort("closed_at", -1))
            
            if not history:
                st.info("No auction history found.")
            else:
                for doc in history:
                    st.markdown(f"**Product ID:** {doc['product_id']} — **Winner:** {doc['winner']} **(${doc['final_bid']})**")
                    for bid in doc.get("bids", []):
                        st.write(f" {bid['timestamp']} — {bid['bidder']} bid ${bid['amount']}")
                    st.divider()
        except Exception as e:
            st.error(f"Could not connect to MongoDB: {e}")
    
    # ============= SELLER - MY AUCTIONS =============
    elif role == "Seller" and page == "My Auctions":
        st.header("My Auctions Overview")
        my_auctions = get_seller_auctions(username)
        
        if not my_auctions:
            st.info("You haven't started any auctions yet.")
        else:
            for a in my_auctions:
                with st.container(border=True):
                    cols = st.columns([1, 3])
                    with cols[0]:
                        st.image(a["image_link"], width=150)
                    with cols[1]:
                        st.markdown(f"**{a['product_name']}**")
                        st.write(f"Auction Code: **{a['auction_code']}**")
                        st.write(f"Base Price: ${a['base_price']}")
                        st.write(f"Status: {'Active' if a['status']=='active' else 'Closed'}")
                        
                        if a['status'] == 'active':
                            st.write(f"Current Bid: ${a.get('current_bid', a['base_price'])}")
                            st.write(f"Highest Bidder: {a.get('current_bidder', 'No bids yet')}")
                        else:
                            st.write(f"Final Bid: ${a.get('final_bid', a['base_price'])}")
                            st.write(f"Winner: {a.get('winner', 'No bids placed')}")
                        
                        st.write(f"Started At: {a['start_time']}")
                        if a.get('end_time'):
                            st.write(f"Ended At: {a['end_time']}")
    
    # ============= LOGOUT =============
    elif page == "Logout":
        cleanup_tcp_client()
        st.session_state.clear()
        st.success("Logged out successfully!")
        st.rerun()