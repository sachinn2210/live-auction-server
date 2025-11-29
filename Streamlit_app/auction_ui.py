import streamlit as st
import subprocess
from pathlib import Path
import psutil
import mysql.connector
import hashlib
from datetime import datetime
from datetime import timezone
import time
# Assuming these imports work and the functions are defined elsewhere or correctly imported
from auction_listener import finalize_mongo_auction
from auction_listener import get_product_from_mongo, save_product_to_mongo, products_col
from auction_listener import add_to_waiting_room, remove_from_waiting_room, get_waiting_users, clear_waiting_room
from bson import ObjectId
import socket
import random
import string
import os
import queue
from streamlit_autorefresh import st_autorefresh
from email_sender import notify_buyers
from urllib.parse import quote_plus, quote
from pymongo import MongoClient
from bson.decimal128 import Decimal128

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "auction_system"
}

# Make paths configurable (server exe only used by admin)
SERVER_EXE = Path(r"D:\TY SEM1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-\Server\AuctionServer.exe")
SERVER_HOST = "127.0.0.1" 
SERVER_PORT = 8000

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
    if user and user.get("password_hash") == hash_password(password):
        return user
    return None

# register_user FUNCTION
def register_user(username, password, role, email=None):
    if user_exists(username):
        st.error("Username already exists.")
        return False
    
    # Use provided email if available, otherwise generate an alias.
    final_email = email.strip() if email else ""
    
    if not final_email:
        if role == "Buyer":
          final_email = f"v.n.s.pavankumar.batchu+{username}@gmail.com"
        elif role == "Seller":
            final_email = f"pavankumar.batchu23+{username}@vit.edu"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, role, email) VALUES (%s, %s, %s, %s)",
        (username, hash_password(password), role, final_email)
    )
    conn.commit()
    conn.close()
    st.success("Registration successful. Please login.")
    return True

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

def generate_auction_code():
    return "AUC-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def insert_auction(product_id: str, product_name: str, base_price: float, duration_minutes: int = 2):
    # Check if product already has an active auction
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT * FROM auctions 
        WHERE product_id=%s AND status='active'
    """, (product_id,))
    
    existing = cursor.fetchone()
    if existing:
        conn.close()
        raise ValueError(f"Product already has an active auction (Code: {existing.get('auction_code')})")
    
    # Check MongoDB status
    try:
        product = products_col.find_one({"_id": ObjectId(product_id)})
        if product and product.get("status") != "available":
            conn.close()
            raise ValueError(f"Product is not available (Status: {product.get('status')})")
    except Exception as e:
        conn.close()
        raise ValueError(f"Could not verify product availability: {e}")
    
    auction_code = generate_auction_code()
    cursor.execute(
        """INSERT INTO auctions
           (product_id, product_name, base_price, status, start_time,
            duration_minutes, created_by, auction_code)
           VALUES (%s,%s,%s,'active',UTC_TIMESTAMP() , %s, %s, %s)""",
        (product_id, product_name[:255], float(base_price),
         int(duration_minutes), st.session_state.username, auction_code)
    )
    auction_id = cursor.lastrowid
    conn.commit()
    conn.close()
    st.session_state.last_auction_code = auction_code

    # Mark product in MongoDB as in_auction
    try:
        products_col.update_one(
            {"_id": ObjectId(product_id)},
            {"$set": {
                "status": "in_auction",
                "auction_code": auction_code,
                "auction_id": auction_id
            }}
        )
    except Exception as e:
        st.warning(f"Could not update product status in MongoDB: {e}")

    return auction_code, auction_id

def close_expired_auctions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='active'")
    active_auctions = cursor.fetchall()

    for auction in active_auctions:
        start = auction.get("start_time")
        duration = auction.get("duration_minutes") or 0

        if not start:
            continue

        # Convert MySQL string timestamps to datetime
        if isinstance(start, str):
            start = datetime.fromisoformat(start)

        # Convert to UTC
        start_utc = start.replace(tzinfo=timezone.utc)
        now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

        # Calculate elapsed seconds
        elapsed = (now_utc - start_utc).total_seconds()

        # Auction expired?
        if elapsed >= duration * 60:
            final_bid = float(auction.get("current_bid") or auction.get("base_price"))
            winner = auction.get("current_bidder", "No Bids")

            # Close in SQL
            cursor.execute("""
                UPDATE auctions 
                SET status='closed', end_time=%s, final_bid=%s, winner=%s
                WHERE id=%s
            """, (datetime.utcnow(), final_bid, winner, auction["id"]))

            print(f"Closed Auction {auction['id']} | Winner: {winner} | Final Bid: {final_bid}")

            # Finalize in MongoDB
            try:
                finalize_mongo_auction(auction["product_id"], winner, float(final_bid))
                products_col.update_one(
                    {"_id": ObjectId(auction["product_id"])},
                    {"$set": {
                        "status": "sold",
                        "sold_to": winner,
                        "sold_price": float(final_bid),
                        "sold_at": datetime.utcnow()
                    }}
                )
            except Exception as e:
                print("Error finalizing Mongo auction:", e)

            # Remove auction row from SQL
            cursor.execute("DELETE FROM auctions WHERE id=%s", (auction["id"],))
            conn.commit()

            # Clear waiting room
            try:
                clear_waiting_room(auction.get("auction_code"))
            except:
                pass

    conn.close()

def get_active_auctions():
    close_expired_auctions()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='active'")
    rows = cursor.fetchall()
    conn.close()
    return rows or []

def get_closed_auctions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE status='closed' ORDER BY end_time DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows or []

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
    return rows or []

def get_auction_by_id(auction_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM auctions WHERE id=%s", (auction_id,))
    row = cursor.fetchone()
    conn.close()
    return row

class TCPClient:
    def __init__(self):
        self.socket = None
        self.connected = False
        self.message_queue = queue.Queue()
        self.error = None
    
    def connect(self, username: str, auction_code: str):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((SERVER_HOST, SERVER_PORT))
            self.socket.settimeout(None)
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
        if self.socket:
            try:
                self.socket.sendall(b"LEAVE\n")
                self.socket.close()
            except:
                pass
        self.connected = False
        self.socket = None

def init_tcp_client():
    if 'tcp_client' not in st.session_state:
        st.session_state.tcp_client = TCPClient()

def cleanup_tcp_client():
    if 'tcp_client' in st.session_state:
        st.session_state.tcp_client.disconnect()
        del st.session_state.tcp_client

AVATAR_COLORS = [
    "#1abc9c","#2ecc71","#3498db","#9b59b6","#34495e","#f39c12","#e67e22","#e74c3c","#7f8c8d"
]

def _color_for_username(username: str):
    if not username:
        return AVATAR_COLORS[0]
    idx = sum(ord(c) for c in username) % len(AVATAR_COLORS)
    return AVATAR_COLORS[idx]

def svg_avatar_data_uri(username: str, size=64):
    initial = (username[0].upper() if username else "?")
    color = _color_for_username(username)
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 {size} {size}'>
      <rect rx='{size//2}' width='{size}' height='{size}' fill='{color}'/>
      <text x='50%' y='50%' font-size='{int(size*0.45)}' text-anchor='middle' fill='white' dy='.35em' font-family='Arial, Helvetica, sans-serif'>{initial}</text>
    </svg>"""
    return "data:image/svg+xml;utf8," + quote(svg, safe='')

def load_css_file(filename="index.css"):
    """Reads the content of the CSS file and wraps it in <style> tags."""
    # This assumes 'styles.css' is in the same directory as auction_ui.py
    css_filepath = Path(__file__).parent / filename
    
    if not css_filepath.exists():
        # You might want to remove this error in production, but helpful for development
        st.error(f"CSS file not found at: {css_filepath}") 
        return ""
    
    try:
        with open(css_filepath, "r") as f:
            css_content = f.read()
            # Wrap the raw CSS content in <style> tags as required by st.markdown
            return f"<style>{css_content}</style>"
    except Exception as e:
        st.error(f"Error reading CSS file: {e}")
        return ""

custom_css = load_css_file("index.css")
st.markdown(custom_css, unsafe_allow_html=True)
# 1. Page Setup
st.set_page_config(page_title="Live Auction Dashboard", layout="wide", initial_sidebar_state="expanded",menu_items={'About': 'A multi-threaded TCP-based live auction system UI.'})
# 2. Custom CSS for a Professional Look (Dark Mode Palette)

st.markdown(custom_css, unsafe_allow_html=True)
st.markdown("<h1 style='text-align: center; color: #3498db;'> 🚀 Live Auction Management Console</h1>", unsafe_allow_html=True)
#st.markdown("---") # Replaced st.divider() with st.markdown("---") for better visual consistency

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.selected_auction = None
    st.session_state.in_auction_room = False
    st.session_state.cached_auction = None
    st.session_state.last_bid_time = 0

# LOGIN / REGISTER
if not st.session_state.logged_in:
    # Use columns to center the login/register forms and make them more compact
    col_login_spacer, col_login, col_reg, col_login_spacer_end = st.columns([1, 2, 2, 1])
    
    with col_login:
        with st.container(border=True): # Use a container for visual separation
            st.markdown("## 🔑 Login")
            st.markdown("<p style='color:black;'>Access your auction dashboard.</p>", unsafe_allow_html=True)
            username = st.text_input("Username", key="login_user", placeholder="Enter your username")
            password = st.text_input("Password", type="password", key="login_pass", placeholder="Enter your password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Login", use_container_width=True, type="primary"):
                user = validate_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.role = user["role"]
                    st.session_state.username = user["username"]
                    st.toast(f"Welcome {user['username']} ({user['role']})!") # Use toast instead of st.success
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    
    with col_reg:
        with st.container(border=True): # Use a container for visual separation
            st.markdown("## 📝 Register")
            st.markdown("<p style='color:black;'>Join the platform as a Buyer, Seller, or Admin.</p>", unsafe_allow_html=True)
            new_user = st.text_input("Username", key="reg_user", placeholder="Choose a username")
            new_pass = st.text_input("Password", type="password", key="reg_pass", placeholder="Choose a strong password")
            new_email = st.text_input("Email (Optional)", key="reg_email", placeholder="Enter your email for notifications")
            role = st.selectbox("Role", ["Admin", "Seller", "Buyer"], index=2)
            if st.button("Register", use_container_width=True):
                if new_user and new_pass:
                    if register_user(new_user, new_pass, role, new_email):
                        pass
                else:
                    st.warning("Please fill all required fields (Username, Password).")

# AUTHENTICATED UI
else:
    role = st.session_state.role
    username = st.session_state.username

    # 2. Refined Sidebar
    with st.sidebar:
        st.markdown(f"## 👤 {username}")
        st.markdown(f"**Role:** <span style='color:  green;'>{role}</span>", unsafe_allow_html=True)

        # Navigation based on role
        nav_options = {
            "Admin": {"Server Control": "⚙️ Server Control", "Bid History": "📜 Bid History", "Closed Auctions": "🔒 Closed Auctions"},
            "Seller": {"Products": "📦 Product Catalog", "My Auctions": "🔨 My Active Auctions"},
            "Buyer": {"Active Auctions": "💰 Live Auctions"}
        }
        
        # Determine the user's page options and select the first one by default
        role_pages = nav_options.get(role, {})
        page_keys = list(role_pages.keys())
        
        # Add a custom styling to the radio buttons to make them look more like tabs/links
        page = st.radio("Go to:", 
                        options=page_keys,
                        format_func=lambda x: role_pages[x],
                        index=page_keys.index(st.session_state.get('current_page', page_keys[0])),
                        key='current_page')
        
        st.markdown("<br><br><br>", unsafe_allow_html=True) # Push to bottom
        if st.button("🚪 Logout", use_container_width=True, type="secondary"):
            cleanup_tcp_client()
            st.session_state.clear()
            st.toast("Logged out successfully!")
            time.sleep(1)
            st.rerun()
    
    # 3. Seller UI: Products (upload + start auctions)
    if role == "Seller" and page == "Products":
        st.header("📦 Product Catalog")
        
        # Upload Form
        st.subheader("⬆️ Upload New Product", help="Add a product to your catalog before starting an auction.")
        with st.expander("Click to add a new product", expanded=False):
            with st.form("upload_form", clear_on_submit=True):
                col_name, col_price = st.columns([3, 1])
                with col_name:
                    product_name = st.text_input("Product Name *", placeholder="Vintage Watch")
                with col_price:
                    base_price = st.number_input("Base Price *", min_value=1.0, step=1.0, format="%.2f")
                
                product_desc = st.text_area("Product Description", placeholder="Brief description of the item...")
                image_file = st.file_uploader("Upload Product Image *", type=["png", "jpg", "jpeg"])
                
                st.markdown("<br>", unsafe_allow_html=True)
                submitted = st.form_submit_button("💾 Save Product to Catalog", type="primary")
                
                if submitted:
                    if not product_name or not image_file:
                        st.error("Product name and image are required.")
                    else:
                        image_bytes = image_file.read()
                        try:
                            pid = save_product_to_mongo(
                                seller=username,
                                name=product_name,
                                description=product_desc,
                                base_price=base_price,
                                image_bytes=image_bytes
                            )
                            st.success(f"Product saved successfully! ID: {pid}")
                        except Exception as e:
                            st.error(f"Could not save product: {e}")
                        st.rerun()

        st.markdown("---")
        st.header("📋 Your Products Overview")

        # Load products
        available_products = list(products_col.find({"seller": username, "status": "available"}))
        in_auction_products = list(products_col.find({"seller": username, "status": "in_auction"}))
        sold_products = list(products_col.find({"seller": username, "status": "sold"}))

        # Use tabs for a cleaner view
        tab_available, tab_in_auction, tab_sold = st.tabs([
            f"Available ({len(available_products)})",
            f"In Auction ({len(in_auction_products)})",
            f"Sold ({len(sold_products)})"
        ])

        # AVAILABLE
        st.subheader("✅ Available for Auction")
        if not available_products:
            st.info("No available products. Please upload one above.")
        else:
            # Use columns and a card-like layout for each product
            cols = st.columns(3, gap="medium") # Create columns for a grid view
            for i, p in enumerate(available_products):
                with cols[i % 3]: # Cycle through the columns
                    with st.container(border=True):
                        st.markdown(f"### {p.get('name')}", unsafe_allow_html=True)
                        image_bytes = None
                        try:
                            _, image_bytes = get_product_from_mongo(str(p["_id"]))
                        except Exception:
                            pass

                        if image_bytes:
                            st.image(image_bytes, caption=p.get('name'), use_container_width=True)
                        else:
                            st.image("https://via.placeholder.com/200x150.png?text=No+Image", use_container_width=True)

                        st.markdown(f"<p style='font-size: 1.2rem;'>*Base Price:* **<span style='color: #f39c12;'>${p.get('base_price', 'N/A')}</span>**</p>", unsafe_allow_html=True)
                        st.write(f"Description: {p.get('description', '')[:50]}...")

                        # Start Auction Form
                        with st.form(f"start_auction_{p['_id']}"):
                            duration_key = f"dur_{p['_id']}"
                            meet_key = f"meet_{p['_id']}"
                            
                            duration = st.number_input("Duration (minutes)", min_value=1, max_value=60, value=2, key=duration_key)
                            meet_link = st.text_input("Google Meet Link", key=meet_key, placeholder="https://meet.google.com/xxxx-xxxx-xxx")

                            if st.form_submit_button(f"🔨 Start Live Auction", type="primary", use_container_width=True):
                                if not meet_link:
                                    st.error("Please provide a Google Meet link to invite buyers.")
                                else:
                                    try:
                                        auction_code, auction_id = insert_auction(
                                            product_id=str(p["_id"]),
                                            product_name=p.get("name"),
                                            base_price=p.get("base_price", 0),
                                            duration_minutes=int(duration)
                                        )
                                        # Notify buyers in background via email (logic unchanged)
                                        start_time = datetime.utcnow().isoformat()
                                        try:
                                            notify_buyers(
                                                product_name=p.get("name"),
                                                auction_code=auction_code,
                                                start_time=start_time,
                                                duration_minutes=int(duration),
                                                meet_link=meet_link,
                                                base_price=p.get("base_price", 0)
                                            )
                                            st.success(f"Auction started! Code: **{auction_code}** — buyers notified.")
                                        except Exception as e:
                                            st.warning(f"Auction started (code {auction_code}) but notify thread failed: {e}")
                                    except Exception as e:
                                        st.error(f"Failed to start auction: {e}")
                                    st.rerun()

        with tab_in_auction:
            if not in_auction_products:
                st.info("No products currently in auction.")
            else:
                for p in in_auction_products:
                    st.warning(f"🟠 **{p.get('name')}** — Auction running (Code: `{p.get('auction_code','N/A')}`). View details in the 'My Auctions' tab.")
        
        with tab_sold:
            if not sold_products:
                st.info("No sold products yet.")
            else:
                for p in sold_products:
                    st.success(f"🎉 **{p.get('name')}** sold to **{p.get('sold_to','N/A')}** for **${p.get('sold_price','N/A')}**")
                    st.caption(f"Code: {p.get('auction_code', 'N/A')} | Sold At: {p.get('sold_at')}")
    # 4. Admin UI: Server Control
    elif role == "Admin" and page == "Server Control":
        st.header("⚙️ Auction Server Control Panel")
        col_status, col_button = st.columns([3, 1])

        if is_server_running():
            col_status.metric(label="Server Status", value="ACTIVE", delta="Running")
            with col_button:
                if st.button("🛑 Stop Server", type="secondary", use_container_width=True):
                    kill_server()
                    st.rerun()
        else:
            col_status.metric(label="Server Status", value="INACTIVE", delta="- Not Running")
            with col_button:
                if st.button("🚀 Start Server", type="primary", use_container_width=True):
                    if not SERVER_EXE.exists():
                        st.error(f"Server executable not found: `{SERVER_EXE}`")
                    else:
                        try:
                            subprocess.Popen([str(SERVER_EXE)], cwd=str(SERVER_EXE.parent),
                                               creationflags=subprocess.CREATE_NEW_CONSOLE)
                            st.success("Auction Server launched successfully.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to start server: {e}")

    # 5. Admin UI: Closed Auctions
    elif role == "Admin" and page == "Closed Auctions":
        st.header("🔒 Closed Auctions Archive")
        closed_auctions = get_closed_auctions()
        if not closed_auctions:
            st.info("No closed auctions yet.")
        else:
           cols = st.columns(2, gap="large") 
           for i, a in enumerate(closed_auctions):
                with cols[i % 2]:
                    with st.container(border=True):
                        prod, image_bytes = (None, None)
                        try:
                            prod, image_bytes = get_product_from_mongo(a.get("product_id"))
                        except Exception:
                            pass
                        
                        col_img, col_info = st.columns([1, 2])
                        with col_img:
                            if image_bytes:
                                st.image(image_bytes, width=120)
                            else:
                                st.image("https://via.placeholder.com/100x75.png?text=Item", width=120)
                        
                        with col_info:
                            st.markdown(f"### {a.get('product_name')}", unsafe_allow_html=True)
                            st.metric("Final Bid", f"${a.get('final_bid') or a.get('base_price')}", help="The final price of the auction.")
                            st.caption(f"Winner: **{a.get('winner', 'N/A')}** | Code: `{a.get('auction_code')}`")
                        
                        with st.expander("Details"):
                            st.write(f"Created By: {a.get('created_by')}")
                            st.write(f"Ended: {a.get('end_time')}")
                            if prod and prod.get('description'):
                                st.caption(f"Description: {prod.get('description')}")

    # 6. Buyer UI: Active Auctions Listing & Join
    elif role == "Buyer" and page == "Active Auctions" and not st.session_state.get("in_auction_room", False):
        st_autorefresh(interval=10000, key="auction_list_refresh")
        st.header("💰 Live Auctions")
        
        # Join by Code - put in a compact container
        with st.container(border=True):
            st.subheader("🎯 Join Auction via Code")
            col_code, col_button = st.columns([3, 1])
            code_input = col_code.text_input("Enter Auction Code (e.g., AUC-1A2B)", label_visibility="collapsed", placeholder="AUC-XXXX")
            if col_button.button("Join Now", use_container_width=True, type="primary"):
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
                cursor.execute("SELECT * FROM auctions WHERE auction_code=%s AND status='active'", (code_input,))
                auction = cursor.fetchone()
                cursor.close()
                conn.close()
                if auction:
                    st.session_state.selected_auction = auction["id"]
                    st.session_state.in_auction_room = True
                    st.rerun()
                else:
                    st.error("Invalid or closed auction code.")

        st.markdown("---")
        st.subheader("Auction Feed")
        auctions = get_active_auctions()
        
        if not auctions:
                st.info("No active auctions right now. Please check back later.")
        else:
                # Use a grid layout for better density
                cols = st.columns(2, gap="large") 
                for i, a in enumerate(auctions):
                    with cols[i % 2]: # Cycle between 2 columns
                        with st.container(border=True):
                            
                            # Timer logic (unchanged)
                            start = a.get("start_time")
                            duration = a.get("duration_minutes") or 0
                            timer = "Unknown"
                            remaining = 0
                            if start:
                                if isinstance(start, str): start = datetime.fromisoformat(start)
                                start_utc = start.replace(tzinfo=timezone.utc)
                                now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                                elapsed = (now_utc - start_utc).total_seconds()
                                remaining = max(0, duration * 60 - elapsed)
                                mins, secs = divmod(int(remaining), 60)
                                timer = f"{mins:02d}:{secs:02d}"
                            
                            # Product info with image
                            image_bytes = None
                            try:
                                _, image_bytes = get_product_from_mongo(a.get("product_id"))
                            except Exception:
                                pass
                            
                            col_img, col_info = st.columns([1, 2])
                            with col_img:
                                if image_bytes:
                                    st.image(image_bytes, width=100)
                                else:
                                    st.image("https://via.placeholder.com/100x75.png?text=Item", width=100)
                                
                            with col_info:
                                st.markdown(f"**{a.get('product_name')}** (`{a.get('auction_code')}`)")
                                st.metric("Current Bid", f"${a.get('current_bid', a.get('base_price'))}", help=f"Highest Bidder: {a.get('current_bidder', 'No bids yet')}")
                                
                                # Use a small alert for the timer
                                # Timer Display Logic
                                timer_color = "#3498db"
                                if remaining < 60 and remaining > 0:
                                     timer_color = "#e74c3c"
                                elif remaining <= 0:
                                     timer_color = "#95a5a6" # Grey for ended
                                else:
                                     st.caption(f"Time Remaining: **{timer}**")
                            
                                st.markdown(f"Time Remaining: <span style='color: {timer_color}; font-weight: bold;'>{timer}</span>", unsafe_allow_html=True)
                                
                                st.metric("Current Bid", f"${a.get('current_bid', a.get('base_price'))}", help=f"Highest Bidder: {a.get('current_bidder', 'No bids yet')}")
                            st.markdown("---")
                            
                            # Waiting Room and Join Button
                            waiting_key = f"waiting_{a.get('auction_code')}"
                            joined = st.session_state.get(waiting_key, False)
                            
                            col_join, col_wait_btn = st.columns(2)
                            
                            with col_join:
                                if st.button(f"➡️ **Join Auction Room**", key=f"join_{a.get('id')}", type="primary", use_container_width=True):
                                    st.session_state.selected_auction = a.get('id')
                                    st.session_state.in_auction_room = True
                                    st.rerun()
                            
                            with col_wait_btn:
                                if not joined:
                                    if st.button("➕ Join Waitlist", key=f"join_wait_{a.get('auction_code')}", use_container_width=True, help="Join the pre-auction waiting list."):
                                        try:
                                            add_to_waiting_room(a.get("auction_code"), username)
                                            st.session_state[waiting_key] = True
                                            st.toast("Joined waiting room! Sellers will be notified.")
                                        except Exception as e:
                                            st.error(f"Could not join waiting room: {e}")
                                        st.rerun()
                                else:
                                    if st.button("Leave Waitlist", key=f"leave_wait_{a.get('auction_code')}", type="secondary", use_container_width=True):
                                        try:
                                            remove_from_waiting_room(a.get("auction_code"), username)
                                            st.session_state[waiting_key] = False
                                            st.info("You've left the waiting room.")
                                        except Exception as e:
                                            st.error(f"Could not leave waiting room: {e}")
                                        st.rerun()
                            
                            # Waiting Room Viewer - use a smaller expander
                            with st.expander(f"👥 View Waiting Room"):
                                waiting_users = get_waiting_users(a.get("auction_code"))
                                if not waiting_users:
                                    st.info("No one in the waiting room yet.")
                                else:
                                    st.write(f"**{len(waiting_users)} buyers waiting:**")
                                    # Display users in a dense layout
                                    wait_cols = st.columns(6)
                                    for idx, user_info in enumerate(waiting_users):
                                        col_idx = idx % 6
                                        with wait_cols[col_idx]:
                                            avatar_url = svg_avatar_data_uri(user_info["username"], size=36)
                                            st.markdown(f"""
                                                <div style="text-align: center; margin: 5px 0;">
                                                    <img src="{avatar_url}" style="border-radius: 50%; width: 36px; height: 36px;">
                                                    <p style="font-size: 10px; margin-top: 2px;">{user_info["username"]}</p>
                                                </div>
                                            """, unsafe_allow_html=True)


    # 7. Buyer UI: Inside Auction Room (Bidding)
    if role == "Buyer" and st.session_state.in_auction_room and st.session_state.selected_auction:
        st_autorefresh(interval=3000, key="auction_room_refresh")
        init_tcp_client()
        auction = get_auction_by_id(st.session_state.selected_auction)
        
        # Handle auction closure/not found
        if not auction or auction.get('status') == 'closed':
            # Use a celebratory success box if the user won, or a warning if it just ended
            if auction and auction.get('winner') == username:
                st.balloons()
                st.success(f"🎉 Congratulations! You won the auction for **{auction.get('product_name')}** with a final bid of **${auction.get('final_bid')}**!")
            else:
                st.warning(f"🔒 This auction for **{auction.get('product_name', 'product')}** has ended.")
                st.info(f"Final Bid: ${auction.get('final_bid', auction.get('base_price'))} | Winner: {auction.get('winner', 'No winner')}")
            
            if st.button("⬅️ Back to Live Auctions", type="primary"):
                cleanup_tcp_client()
                st.session_state.in_auction_room = False
                st.session_state.selected_auction = None
                st.session_state.cached_auction = None
                st.rerun()
            st.stop() # Stop further execution if closed/not found

        # Handle connection failure
        tcp_client = st.session_state.tcp_client
        if not tcp_client.connected:
            success, error = tcp_client.connect(username, auction.get("auction_code"))
            if not success:
                st.error(f"❌ Connection failed: {error}. Make sure the Auction Server is running.")
                col_retry, col_back = st.columns(2)
                if col_retry.button("🔄 Retry Connection", type="primary"):
                    st.rerun()
                if col_back.button("⬅️ Back to Active Auctions"):
                    cleanup_tcp_client()
                    st.session_state.in_auction_room = False
                    st.session_state.selected_auction = None
                    st.rerun()
                st.stop() # Stop further execution if connection failed
            else:
                st.toast(f"✅ Connected to auction {auction.get('auction_code')}!")

        # Main Auction Room UI
        st.header(f"🔨 Auction Room — {auction.get('product_name')}")
        
        current_bid = auction.get("current_bid") or auction.get("base_price")
        current_bidder = auction.get("current_bidder") or "No bids yet"
        
        # Top-level metrics for quick info
        col_m1, col_m2, col_m3 = st.columns(3)
        delta_text = ""
        delta_color = "off"
        if current_bidder == username:
            delta_text = "Winning"
            delta_color = "normal"
        elif current_bidder != "No bids yet":
            delta_text = "Outbid"
            delta_color = "inverse" # Red delta
        else:
            delta_text = "Start Bid"
            delta_color = "off"
        col_m1.metric("Current Highest Bid", f"${current_bid}", delta=delta_text, delta_color=delta_color)
        col_m2.metric("Highest Bidder", current_bidder, help="The user currently in the lead.")
        col_m3.metric("Base Price", f"${auction.get('base_price')}")
        
        st.markdown("---")
        
        col_image, col_timer_bid = st.columns([1, 2])
        
        # Product Image and Info
        with col_image:
         with st.container(border=True):
            image_bytes = None
            try:
                prod, image_bytes = get_product_from_mongo(auction.get("product_id"))
            except Exception:
                prod = None
                
            if image_bytes:
                st.image(image_bytes, caption=auction.get('product_name'), use_container_width=True)
            else:
                st.image("https://via.placeholder.com/250x200.png?text=Product+Image", use_container_width=True)
            
            if prod and prod.get('description'):
                with st.expander("Product Description"):
                    st.write(prod.get('description'))
        
        # Timer and Bidding Form
        with col_timer_bid:
         with st.container(border=True):
            # Timer Block (unchanged logic, refined display)
            start_time = auction.get("start_time")
            duration = auction.get("duration_minutes") or 0
            
            remaining = 0
            timer_display = "N/A"
            if start_time:
                if isinstance(start_time, str): start_time = datetime.fromisoformat(start_time)
                start_utc = start_time.replace(tzinfo=timezone.utc)
                now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)
                elapsed = (now_utc - start_utc).total_seconds()
                remaining = max(0, duration * 60 - elapsed)
                mins, secs = divmod(int(remaining), 60)
                timer_display = f"{mins:02d}:{secs:02d}"

           # Display Timer prominently (using HTML for large font and color)
                if remaining <= 0:
                    st.markdown(f"<h2 style='text-align: center; color: #e74c3c;'>🔒 AUCTION ENDED</h2>", unsafe_allow_html=True)
                elif remaining < 30:
                    st.markdown(f"<h2 style='text-align: center; color: #e74c3c;'>🔥 LAST CHANCE: {timer_display}</h2>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<h2 style='text-align: center; color: #3498db;'>⏱️ Time Left: {timer_display}</h2>", unsafe_allow_html=True)

            st.markdown("---")
            st.subheader("Place Your Bid")
            min_bid = float(current_bid) + 1.0
            
            if remaining <= 0:
                    st.error("Bidding is closed as the auction has ended.")
            else:
             with st.form(key="bid_form", clear_on_submit=True):
                bid_value = st.number_input(
                    "Enter your bid amount",
                    min_value=min_bid,
                    value=min_bid,
                    format="%.2f",
                    help=f"Minimum next bid: ${min_bid:.2f}"
                )
                submitted = st.form_submit_button("🔨 Place Bid", type="primary", use_container_width=True)
                
                if submitted:
                    current_time = time.time()
                    if current_time - st.session_state.last_bid_time < 1:
                        st.error("🚫 Please wait a moment (1s cooldown) before placing another bid.")
                    else:
                        success, error = tcp_client.send_bid(bid_value, username, auction.get("auction_code"))
                        if success:
                            st.toast(f"✅ Bid of ${bid_value} sent!")
                            st.session_state.last_bid_time = current_time
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"❌ Failed to send bid: {error}. Attempting to reconnect...")
                            cleanup_tcp_client()
                            st.rerun()
            
            st.markdown("---")
            if st.button("⬅️ Leave Auction Room", use_container_width=True, type="secondary"):
                cleanup_tcp_client()
                st.session_state.in_auction_room = False
                st.session_state.selected_auction = None
                st.session_state.cached_auction = None
                st.rerun()

    # 8. Admin UI: Bid History (MongoDB)
    elif role == "Admin" and page == "Bid History":
        st.header("📜  Bid History ")
        try:
            client = MongoClient("mongodb://localhost:27017")
            db = client["auction_data"]
            # Use st.cache_data to speed up UI loading if history is large
            @st.cache_data(ttl=60) 
            def load_history():
                return list(db["auction_history"].find().sort("closed_at", -1))
            
            history = load_history()
            
            if not history:
                st.info("No completed auction history found.")
            else:
                for doc in history:
                    # Use a clean container for each auction history
                    with st.container(border=True):
                        # ---- Sanitize values safely ----
                        product_name = str(doc.get("product_name") or "N/A")
                        auction_code = str(doc.get("auction_code") or "N/A")

                        closed_at = doc.get("closed_at")
                        if hasattr(closed_at, "strftime"):
                            closed_at_str = closed_at.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            closed_at_str = str(closed_at) if closed_at else "N/A"

                        # Final bid formatting
                        final_bid_raw = doc.get("final_bid")
                        from bson.decimal128 import Decimal128
                        try:
                            if isinstance(final_bid_raw, Decimal128):
                                final_bid = f"{float(final_bid_raw.to_decimal()):.2f}"
                            else:
                                final_bid = f"{float(final_bid_raw):.2f}"
                        except:
                            final_bid = str(final_bid_raw)

                        winner = str(doc.get("winner") or "No Bids")

                        # ---- Styled HTML block (matches your theme & card layout) ----
                        st.markdown(f"""
                        <div class="bid-card">
                            <div class="bid-title">{product_name}</div>
                            <div class="bid-subinfo">
                                <b>Code:</b> {auction_code} &nbsp; | &nbsp;
                                <b>Ended:</b> {closed_at_str}
                            </div>
                            <div class="bid-winner-box">
                                Winner: <b>{winner}</b> &nbsp; | &nbsp;
                                Final Price: <span>${final_bid}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)

                        
                        # Use an expander for the individual bids
                        with st.expander("View All Bids"):
                            bids = doc.get("bids", [])
                            if not bids:
                                st.write("No individual bids recorded.")
                            else:
                                st.markdown("##### Bid Log (Newest First)")
                                st.table([
                                    {
                                        "Time (UTC)": bid.get('timestamp'),
                                        "Bidder": bid.get('bidder'),
                                        "Amount": f"${float(bid.get('amount').to_decimal()):.2f}" if isinstance(bid.get('amount'), Decimal128) else f"${bid.get('amount'):.2f}"
                                    }
                                    for bid in sorted(bids, key=lambda x: x.get("timestamp"), reverse=True)
                                ])
                   
        except Exception as e:
            st.error(f"Could not connect to MongoDB or load history: {e}")

    # 9. Seller UI: My Auctions
    elif role == "Seller" and page == "My Auctions":
        
        st.header("🔨 My Auctions Overview")
        my_auctions = get_seller_auctions(username)
        if not my_auctions:
            st.info("You haven't started any auctions yet.")
        else:
            active_auctions = [a for a in my_auctions if a.get('status') == 'active']
            closed_auctions = [a for a in my_auctions if a.get('status') == 'closed']
            
            tab_active, tab_closed = st.tabs([f"Active ({len(active_auctions)})", f"Closed History ({len(closed_auctions)})"])
            with tab_active:
                if not active_auctions:
                    st.info("No auctions are currently running.")
                else:
                    for a in active_auctions:
                        with st.container(border=True):
                            col_img, col_info, col_controls = st.columns([1, 2, 1])
                            
                            # Image column
                            with col_img:
                                image_bytes = None
                                try:
                                    _, image_bytes = get_product_from_mongo(a.get("product_id"))
                                except Exception:
                                    pass
                                if image_bytes:
                                    st.image(image_bytes, width=100)
                                else:
                                    st.image("https://via.placeholder.com/100x75.png?text=Item", width=100)
                            
                            # Info column
                            with col_info:
                                st.markdown(f"**{a.get('product_name')}** (`{a.get('auction_code')}`)")
                                st.markdown(f"Status: <span style='color: #2ecc71;'>**ACTIVE**</span>", unsafe_allow_html=True)
                                st.write(f"Base Price: **${a.get('base_price')}**")
                                st.metric("Current Bid", f"${a.get('current_bid', a.get('base_price'))}", help=f"Highest Bidder: {a.get('current_bidder', 'No bids yet')}")
                            
                            # Controls column
                            with col_controls:
                                # Show Waiting Room in a small expander
                                with st.expander(f"👥 Waitlist"):
                                    waiting_users = get_waiting_users(a.get('auction_code'))
                                    if waiting_users:
                                        st.write(f"**{len(waiting_users)} buyers waiting**")
                                        # Show only first few users
                                        for user_info in waiting_users[:3]:
                                            st.caption(f"- {user_info['username']}")
                                        if len(waiting_users) > 3:
                                            st.caption(f"...and {len(waiting_users) - 3} more.")
                                    else:
                                        st.caption("No buyers waiting yet.")

                                st.markdown("---")
                                # Manual end auction button (logic unchanged, UI cleaner)
                                end_key = f"confirm_end_{a['id']}"
                                if not st.session_state.get(end_key, False):
                                    if st.button(f"🛑 End Early", key=f"end_{a['id']}", type="secondary", use_container_width=True):
                                        st.session_state[end_key] = True
                                        st.rerun()
                                else:
                                    st.error("⚠️ Confirm End Auction?")
                                    col_yes, col_no = st.columns(2)
                                    with col_yes:
                                        if st.button("✅ YES", key=f"confirm_yes_{a['id']}", type="primary", use_container_width=True):
                                            # Logic to close auction early (unchanged)
                                            try:
                                                conn = get_db_connection()
                                                cursor = conn.cursor()
                                                
                                                raw = a.get("current_bid") or a.get("base_price")
                                                final_bid = float(raw)

                                                winner = a.get("current_bidder", "No Bids")
                                                
                                                cursor.execute("""
                                                    UPDATE auctions 
                                                    SET status='closed', end_time=UTC_TIMESTAMP(), final_bid=%s, winner=%s
                                                    WHERE id=%s
                                                """, (final_bid, winner, a["id"]))
                                                conn.commit()
                                                
                                                # Finalize in MongoDB
                                                finalize_mongo_auction(a["product_id"], winner, float(final_bid))
                                                products_col.update_one(
                                                    {"_id": ObjectId(a["product_id"])},
                                                    {"$set": {
                                                        "status": "sold",
                                                        "sold_to": winner,
                                                        "sold_price": float(final_bid),
                                                        "sold_at": datetime.utcnow()
                                                    }}
                                                )
                                                
                                                # Delete from MySQL
                                                cursor.execute("DELETE FROM auctions WHERE id=%s", (a["id"],))
                                                conn.commit()
                                                
                                                # Clear waiting room
                                                clear_waiting_room(a.get("auction_code"))
                                                
                                                st.success(f"✅ Auction ended! Winner: {winner}, Final Bid: ${final_bid}")
                                                st.session_state[end_key] = False
                                                time.sleep(1)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Failed to end auction: {e}")
            
                                        with col_no:
                                            if st.button("❌ NO", key=f"cancel_end_{a['id']}", use_container_width=True):
                                                st.session_state[end_key] = False
                                                st.rerun()

            with tab_closed :
                if not closed_auctions:
                    st.info("No auctions have been closed yet.")
                else:
                    for a in closed_auctions:
                        with st.container(border=True):
                            col_info, col_details = st.columns([2, 1])
                            with col_info:
                                st.markdown(f"**{a.get('product_name')}** (`{a.get('auction_code')}`)")
                                st.markdown(f"Status: <span style='color: #e74c3c;'>**CLOSED**</span>", unsafe_allow_html=True)
                                st.write(f"Winner: **{a.get('winner', 'No bids placed')}**")
                                st.success(f"Final Bid: **${a.get('final_bid', a.get('base_price'))}**")
                            with col_details:
                                st.caption(f"Started: {a.get('start_time')}")
                                if a.get('end_time'):
                                    st.caption(f"Ended: {a.get('end_time')}")