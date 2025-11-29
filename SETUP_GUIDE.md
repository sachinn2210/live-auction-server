# 🚀 Complete Setup & Run Guide

This guide will walk you through setting up and running the Multithreaded TCP-Based Live Auction Server with the beautiful Streamlit UI.

---

## 📋 Prerequisites

Make sure you have the following installed:

- **Windows OS** (required for Winsock2)
- **g++ compiler** (version 10 or higher) - for C++ compilation
- **Python 3.8+** - for Python components
- **MySQL Server** - for database
- **MongoDB** - for document storage
- **Git** (optional) - for cloning

---

## 🔧 Step-by-Step Setup

### Step 1: Build the C++ Server

1. Open **PowerShell** or **Command Prompt**
2. Navigate to the Server directory:
   ```powershell
   cd Server
   ```

3. Compile the server:
   ```powershell
   g++ -std=c++17 AuctionServer.cpp main.cpp -o AuctionServer.exe -lws2_32
   ```

4. ✅ You should see `AuctionServer.exe` created in the Server folder

---

### Step 2: Setup MySQL Database

1. Start MySQL service (if not running):
   ```powershell
   # Usually MySQL starts automatically, but if not:
   net start MySQL80
   ```

2. Login to MySQL:
   ```powershell
   mysql -u root -p
   ```
   (Enter your MySQL root password)

3. Create the database and tables:
   ```sql
   CREATE DATABASE auction_system;
   USE auction_system;

   CREATE TABLE users (
     id INT AUTO_INCREMENT PRIMARY KEY,
     username VARCHAR(255) UNIQUE NOT NULL,
     password_hash VARCHAR(255) NOT NULL,
     role ENUM('Admin','Seller','Buyer') DEFAULT 'Buyer',
     email VARCHAR(255),
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );

   CREATE TABLE auctions (
     id INT AUTO_INCREMENT PRIMARY KEY,
     product_id VARCHAR(255) NOT NULL,
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

4. Exit MySQL:
   ```sql
   exit;
   ```

---

### Step 3: Start MongoDB

1. Open a **new PowerShell/Command Prompt** window
2. Start MongoDB:
   ```powershell
   mongod
   ```
   (Keep this window open - MongoDB needs to keep running)

---

### Step 4: Setup Python Environment

1. Navigate to the project root:
   ```powershell
   cd E:\College\TY_25-26\SEM_1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-
   ```

2. Create a virtual environment:
   ```powershell
   python -m venv DAAenv
   ```

3. Activate the virtual environment:
   ```powershell
   DAAenv\Scripts\activate
   ```
   (You should see `(DAAenv)` in your prompt)

4. Install required Python packages:
   ```powershell
   pip install streamlit
   pip install mysql-connector-python
   pip install pymongo
   pip install websockets
   pip install streamlit-autorefresh
   pip install psutil
   ```

   Or install all at once:
   ```powershell
   pip install streamlit mysql-connector-python pymongo websockets streamlit-autorefresh psutil
   ```

---

### Step 5: Configure Database Credentials

1. Open `Streamlit_app/auction_listener.py`
2. Update the MySQL credentials (lines 19-26) if needed:
   ```python
   DB_CONFIG = {
       "host": "localhost",
       "user": "root",
       "password": "123456",  # Change to your MySQL password
       "database": "auction_system",
       ...
   }
   ```

3. Open `Streamlit_app/auction_ui.py`
4. Update the MySQL credentials (lines 26-31) if needed:
   ```python
   DB_CONFIG = {
       "host": "localhost",
       "user": "root",
       "password": "123456",  # Change to your MySQL password
       "database": "auction_system"
   }
   ```

5. Update the server executable path (line 34) if needed:
   ```python
   SERVER_EXE = Path(r"D:\TY SEM1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-\Server\AuctionServer.exe")
   ```
   Change to your actual path!

---

### Step 6: Configure Email (Optional)

If you want email notifications to work:

1. Open `Streamlit_app/email_sender.py`
2. Set environment variables or update the code with your SMTP credentials:
   ```powershell
   # In PowerShell, set environment variables:
   $env:SMTP_USER = "your-email@gmail.com"
   $env:SMTP_PASS = "your-app-password"
   $env:SMTP_SELLER = "seller-email@domain.com"
   $env:SMTP_SELLER_PASS = "seller-app-password"
   ```

   (Note: For Gmail, you need to use an App Password, not your regular password)

---

## 🚀 Running the Application

You need to run **3 components** in separate terminal windows:

### Terminal 1: C++ Auction Server

1. Open PowerShell/Command Prompt
2. Navigate to Server directory:
   ```powershell
   cd Server
   ```

3. Run the server:
   ```powershell
   .\AuctionServer.exe
   ```

4. ✅ You should see:
   ```
   Starting auction server
   Winsock initialized successfully.
   Server socket listening on port 8000...
   Waiting for clients to connect...
   ```

   **Keep this window open!**

---

### Terminal 2: Python Listener

1. Open a **new** PowerShell/Command Prompt
2. Activate the virtual environment:
   ```powershell
   cd E:\College\TY_25-26\SEM_1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-
   DAAenv\Scripts\activate
   ```

3. Navigate to Streamlit_app:
   ```powershell
   cd Streamlit_app
   ```

4. Run the listener:
   ```powershell
   python auction_listener.py
   ```

5. ✅ You should see:
   ```
   ✅ MySQL connection pool initialized
   🚀 Starting WebSocket server on ws://0.0.0.0:8765
   ✅ Connected to Auction Server as Monitor Client
   ```

   **Keep this window open!**

---

### Terminal 3: Streamlit Web UI

1. Open a **new** PowerShell/Command Prompt
2. Activate the virtual environment:
   ```powershell
   cd E:\College\TY_25-26\SEM_1\CN\CP\Multithreaded-TCP-Based-Live-Auction-Server-
   DAAenv\Scripts\activate
   ```

3. Run Streamlit:
   ```powershell
   streamlit run Streamlit_app/auction_ui.py
   ```

4. ✅ Your browser should automatically open to:
   ```
   http://localhost:8501
   ```

   If not, manually open your browser and go to that URL.

---

## 🎯 Using the Application

### First Time Setup:

1. **Register an Admin Account:**
   - On the login page, use the Register form
   - Choose username, password, and select **"Admin"** as role
   - Click Register

2. **Login:**
   - Use your admin credentials to login

3. **Start the Server (if not running):**
   - As Admin, go to "⚙️ Server Control"
   - Click "🚀 Start Server" if it shows INACTIVE
   - Wait a few seconds for it to start

4. **Create Test Accounts:**
   - Logout and register a **Seller** account
   - Register a **Buyer** account

### As a Seller:

1. Login as Seller
2. Go to "📦 Product Catalog"
3. Upload a product:
   - Fill in product name, description, base price
   - Upload an image
   - Click "💾 Save Product to Catalog"
4. Start an auction:
   - Find your product in "Available" tab
   - Enter duration and Google Meet link
   - Click "🔨 Start Live Auction"
   - Note the auction code (e.g., AUC-1A2B)

### As a Buyer:

1. Login as Buyer
2. Go to "💰 Live Auctions"
3. Join an auction:
   - Either enter the auction code in "Join Auction via Code"
   - Or click "➡️ Join Auction Room" on any active auction
4. Place bids:
   - Enter your bid amount (must be higher than current bid)
   - Click "🔨 Place Bid"
   - Watch real-time updates!

### As an Admin:

1. View all closed auctions
2. View bid history from MongoDB
3. Start/Stop the C++ server
4. Monitor system status

---

## 🐛 Troubleshooting

### Issue: "Server executable not found"
- **Solution:** Update the `SERVER_EXE` path in `auction_ui.py` line 34 to match your actual path

### Issue: "MySQL connection failed"
- **Solution:** 
  - Make sure MySQL is running: `net start MySQL80`
  - Check credentials in `auction_listener.py` and `auction_ui.py`
  - Verify database `auction_system` exists

### Issue: "MongoDB connection failed"
- **Solution:** 
  - Make sure MongoDB is running: `mongod`
  - Check if MongoDB service is started

### Issue: "Cannot connect to Auction Server"
- **Solution:**
  - Make sure `AuctionServer.exe` is running (Terminal 1)
  - Check if port 8000 is not blocked by firewall
  - Verify the server shows "listening on port 8000"

### Issue: "Module not found" errors
- **Solution:**
  - Make sure virtual environment is activated: `DAAenv\Scripts\activate`
  - Reinstall packages: `pip install streamlit mysql-connector-python pymongo websockets streamlit-autorefresh psutil`

### Issue: Streamlit UI looks broken
- **Solution:**
  - Make sure `index.css` is in the `Streamlit_app/` folder
  - Clear browser cache and refresh
  - Check browser console for errors (F12)

---

## 📝 Quick Command Reference

```powershell
# Build Server
cd Server
g++ -std=c++17 AuctionServer.cpp main.cpp -o AuctionServer.exe -lws2_32

# Activate Python Environment
DAAenv\Scripts\activate

# Run Server (Terminal 1)
cd Server
.\AuctionServer.exe

# Run Listener (Terminal 2)
cd Streamlit_app
python auction_listener.py

# Run Streamlit UI (Terminal 3)
streamlit run Streamlit_app/auction_ui.py
```

---

## 🎨 Features Overview

- ✨ **Beautiful Modern UI** with animations and glassmorphism
- 🔄 **Real-time Updates** via WebSocket
- 💰 **Live Bidding** with TCP socket communication
- 📊 **Database Integration** (MySQL + MongoDB)
- 👥 **Role-based Access** (Admin, Seller, Buyer)
- 📧 **Email Notifications** (optional)
- ⏱️ **Timer-based Auctions** with automatic expiration
- 🎯 **Waiting Room** for pre-auction interest

---

## 🎉 You're All Set!

Once all three terminals are running and the browser is open, you should see the beautiful auction dashboard. Start by registering accounts and creating your first auction!

**Need Help?** Check the console outputs in each terminal for error messages.

