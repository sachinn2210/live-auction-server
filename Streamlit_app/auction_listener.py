import socket
import asyncio
import json
import mysql.connector
from datetime import datetime
from pymongo import MongoClient
import websockets
import re
from mysql.connector import pooling
import logging

# --- Configuration ---
SERVER_IP = "127.0.0.1"
SERVER_PORT = 8000
WS_HOST = "0.0.0.0"
WS_PORT = 8765

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "123456",
    "database": "auction_system",
    "pool_name": "auction_pool",
    "pool_size": 5
}

MONGO_URI = "mongodb://localhost:27017"

# --- Setup logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# --- MongoDB ---
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client["auction_data"]
active_col = mongo_db["active_auctions"]
history_col = mongo_db["auction_history"]

# --- MySQL connection pool ---
connection_pool = None

def init_db_pool():
    global connection_pool
    if connection_pool is None:
        connection_pool = pooling.MySQLConnectionPool(**DB_CONFIG)
        log.info("MySQL connection pool initialized")

def get_db_connection():
    if connection_pool is None:
        init_db_pool()
    return connection_pool.get_connection()

def update_current_bid_by_code(new_bid: float, bidder_id: str, auction_code: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE auctions
            SET current_bid=%s, current_bidder=%s, last_update=NOW()
            WHERE auction_code=%s AND status='active'
        """, (new_bid, bidder_id, auction_code))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        log.error(f"Error updating bid in MySQL for {auction_code}: {e}")

def get_product_id_by_code(auction_code: str):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT product_id FROM auctions WHERE auction_code=%s AND status='active' LIMIT 1", (auction_code,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        log.warning(f"Error looking up auction_code {auction_code}: {e}")
        return None

def log_bid_to_mongo(product_id, bidder, bid_value):
    try:
        bid_entry = {
            "bidder": bidder,
            "amount": float(bid_value),
            "timestamp": datetime.utcnow()
        }
        active_col.update_one(
            {"product_id": product_id},
            {"$push": {"bids": bid_entry},
             "$set": {"last_bid": bid_value, "last_bidder": bidder, "last_update": datetime.utcnow()}},
            upsert=True
        )
        log.info(f"MongoDB updated for {product_id}: {bidder} → {bid_value}")
    except Exception as e:
        log.error(f"Error logging to MongoDB: {e}")

def finalize_mongo_auction(product_id, winner, final_bid):
    try:
        doc = active_col.find_one({"product_id": product_id})
        if doc:
            doc["winner"] = winner
            doc["final_bid"] = final_bid
            doc["closed_at"] = datetime.utcnow()
            history_col.insert_one(doc)
            active_col.delete_one({"product_id": product_id})
            log.info(f"Moved {product_id} → auction_history")
    except Exception as e:
        log.error(f"Error finalizing auction: {e}")

def parse_bid_message(msg: str):
    try:
        msg = msg.strip()
        # Updated regex for bid messages that include auction_code
        if "NEW HIGH BID!" in msg:
            match = re.search(r'NEW HIGH BID!\s+([\d.]+)\s+by\s+(\S+)\s+in\s+(AUC-[A-Z0-9]+)', msg)
            if match:
                bid = float(match.group(1))
                bidder = match.group(2).strip()
                auction_code = match.group(3).strip()
                return bid, bidder, auction_code
        # Parse join messages
        if "[JOIN]" in msg:
            match = re.search(r'\[JOIN\]\s+(\S+)\s+joined\s+(AUC-[A-Z0-9]+)', msg)
            if match:
                username = match.group(1)
                auction_code = match.group(2)
                return None, {"type": "join", "username": username, "auction_code": auction_code}, None
    except Exception as e:
        log.warning(f"Parse error: {e} — msg: {msg}")
    return None, None, None

connected_websockets = set()

async def ws_handler(websocket):
    connected_websockets.add(websocket)
    remote = websocket.remote_address
    log.info(f"WebSocket client connected from {remote}")
    try:
        async for message in websocket:
            log.debug(f"WS message from {remote}: {message}")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        log.warning(f"WebSocket error: {e}")
    finally:
        connected_websockets.discard(websocket)
        log.info(f"WebSocket client disconnected from {remote}")

async def broadcast_ws(msg_dict):
    if not connected_websockets:
        return
    payload = json.dumps(msg_dict, default=str)
    disconnected = set()
    for ws in connected_websockets:
        try:
            await ws.send(payload)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(ws)
        except Exception as e:
            log.warning(f"Error sending to WebSocket: {e}")
            disconnected.add(ws)
    connected_websockets.difference_update(disconnected)

async def tcp_monitor_loop():
    retry_delay = 5
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            log.info(f"🔌 Connecting to Auction Server at {SERVER_IP}:{SERVER_PORT}...")
            sock.connect((SERVER_IP, SERVER_PORT))
            sock.settimeout(None)
            sock.sendall(b"MONITOR_CLIENT\n")
            log.info("Connected to Auction Server as Monitor Client")
            buffer = ""
            loop = asyncio.get_running_loop()
            while True:
                data = await loop.run_in_executor(None, sock.recv, 1024)
                if not data:
                    log.warning("Connection closed by server")
                    break
                buffer += data.decode(errors="ignore")
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    msg = line.strip()
                    if not msg:
                        continue
                    log.info(f"[TCP BROADCAST] {msg}")
                    bid, bidder, auction_code = parse_bid_message(msg)
                    if bid is not None and bidder and auction_code:
                        product_id = get_product_id_by_code(auction_code)
                        if product_id:
                            update_current_bid_by_code(bid, bidder, auction_code)
                            log_bid_to_mongo(product_id, bidder, bid)
                            update = {
                                "type": "bid_update",
                                "auction_code": auction_code,
                                "product_id": product_id,
                                "bid": bid,
                                "bidder": bidder,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                            await broadcast_ws(update)
                    elif isinstance(bidder, dict) and bidder.get("type") == "join":
                        join_update = {
                            "type": "user_joined",
                            "username": bidder["username"],
                            "auction_code": bidder["auction_code"],
                            "timestamp": datetime.utcnow().isoformat()
                        }
                        await broadcast_ws(join_update)
        except ConnectionRefusedError:
            log.error(f"Could not connect to Auction Server. Retrying in {retry_delay}s...")
        except socket.timeout:
            log.warning(f"Connection timeout. Retrying in {retry_delay}s...")
        except Exception as e:
            log.exception(f"Error in TCP monitor: {e}")
        finally:
            try:
                sock.close()
            except Exception:
                pass
            log.info(f"🔌 Disconnected from Auction Server. Retrying in {retry_delay}s...")
        await asyncio.sleep(retry_delay)

async def main():
    init_db_pool()
    log.info(f"Starting WebSocket server on ws://{WS_HOST}:{WS_PORT}")
    ws_server = await websockets.serve(ws_handler, WS_HOST, WS_PORT)
    log.info("WebSocket server ready")
    tcp_task = asyncio.create_task(tcp_monitor_loop())
    try:
        await tcp_task
    except asyncio.CancelledError:
        log.info("TCP monitor cancelled")
    finally:
        ws_server.close()
        await ws_server.wait_closed()
        log.info("Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("\n\nShutting down gracefully...")
    except Exception as e:
        log.exception(f" Fatal error: {e}")