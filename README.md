#  Multithreaded TCP Based Live Auction Server (C++)

This project implements a real-time live auction system built on top of **C++, Python, MySQL, and MongoDB**.
It combines a **multithreaded TCP server (C++)** with a Python listener and a **Streamlit web frontend** to create a fully integrated, end-to-end auction experience.

---

##  Components Overview
| Component      | Technology                        | Description                                                                                   |
| -------------- | --------------------------------- | --------------------------------------------------------------------------------------------- |
| **Server**     | C++ (Winsock2, Threads)        | Handles all auction bid/join messages via TCP sockets                                         |
| **Listener**   | Python (`auction_listener.py`) | Connects as a monitor client to the server, updates MySQL & MongoDB, broadcasts via WebSocket |
| **Web UI**     | Streamlit (`auction_ui.py`)    | Frontend for Admin, Seller, Buyer roles                                                       |
| **Database 1** | MySQL                         | Stores users, active auctions, auction state                                                  |
| **Database 2** |  MongoDB                        | Logs bids and archives completed auctions                                                     |

##  Features
 C++ Auction Server

Multithreaded TCP socket server using Winsock2

Handles concurrent client connections

Manages auction rooms and broadcasting

Special monitor client for Python listener integration

 Python Auction Listener

Connects to the server as a MONITOR_CLIENT

Parses join/bid messages such as

[JOIN] Alice joined AUC-1A2B
NEW HIGH BID! 155.00 by Bob in AUC-1A2B


Updates MySQL (current_bid, current_bidder)

Logs bid details in MongoDB

Provides a WebSocket (ws://localhost:8765) for live frontend updates

 Streamlit Web Interface

Role-based access: Admin, Seller, Buyer

Admin: Start/stop server, view closed auctions & MongoDB history

Seller: Start auctions from product catalog (train.csv)

Buyer: Join auctions, place bids, and see live bid updates
---

##  Requirements

Make sure the following are installed:

| Requirement | Version |
|-------------|----------|
| g++ compiler | **10 or higher** |
| Git | Latest |
| Windows OS |  Supported |
| Visual Studio Code (optional) | Recommended |

>  Ensure that your **g++ version is 10 or higher**, as this project uses modern **C++17 features and multithreading** (`<thread>`, `<mutex>`).

---

##  Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/Pavankumar-Batchu1185/Multithreaded-TCP-Based-Live-Auction-Server-
cd Multithreaded-TCP-Based-Live-Auction-Server-
```

### 2. Build the Server
```bash
cd server
g++ -std=c++17 AuctionServer.cpp main.cpp -o AuctionServer.exe -lws2_32
```

### 3.Build the Client
```bash
cd ../client
g++ -std=c++17 AuctionClient.cpp main.cpp -o AuctionClient.exe -lws2_32
```

## Run the application
### 1.Start the server
```bash
cd server
./AuctionServer.exe
```
You can open up to 10 client windows to simulate multiple bidders.

3️⃣ Setup MySQL Database

Login and create schema:
```bash
mysql -u root -p
```

Execute:
```bash
CREATE DATABASE auction_system;
USE auction_system;

CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('Admin','Seller','Buyer') DEFAULT 'Buyer',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE auctions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_id INT NOT NULL,
  product_name VARCHAR(255),
  image_link VARCHAR(500),
  base_price DECIMAL(10,2),
  status ENUM('active','closed') DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  duration_minutes INT DEFAULT 2,
  end_time TIMESTAMP NULL,
  final_bid DECIMAL(10,2) DEFAULT 0,
  winner VARCHAR(255),
  current_bid DECIMAL(10,2),
  current_bidder VARCHAR(255),
  last_update TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
  created_by VARCHAR(255),
  auction_code VARCHAR(20)
);
```
4️⃣ Start MongoDB

Make sure MongoDB is running:
```bash
mongod
```
5️⃣ Setup Python Environment
```bash
python -m venv DAAenv
DAAenv\Scripts\activate
pip install -r requirements.txt
```

6️⃣ Run the Python Listener
```bash
cd Streamlit_app
python auction_listener.py
```

✅ Expected logs:

✅ MySQL connection pool initialized
🚀 Starting WebSocket server on ws://0.0.0.0:8765
✅ Connected to Auction Server as Monitor Client

7️⃣ Launch the Streamlit Dashboard
```bash
streamlit run Streamlit_app/auction_ui.py
```

Access locally at 👉 http://localhost:8501

8️⃣ (Optional) Expose Publicly via Ngrok
```bash
ngrok config add-authtoken <your-token>
ngrok http --domain=stylish-onie-slung.ngrok-free.app 8501
```

🌐 Visit: https://stylish-onie-slung.ngrok-free.app

## Project Structure
```css
.
├── server
│   ├── AuctionServer.cpp
│   ├── main.cpp
    ├── AuctionServer.h
    ├── server.md
├── client
│   ├── AuctionClient.cpp
│   ├── main.cpp
├──  Streamlit_app/
│   ├── auction_listener.py    
│   ├── auction_ui.py          
│
├── train.csv                   
├── README.md                  
└── requirements.txt            
```
The old client/ directory is now not used —
all buyer/seller interactions are handled via auction_ui.py.
